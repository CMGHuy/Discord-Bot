"""v174 § 5: intermarket diagnostics, printed beside the verdict, never gating."""
import functools
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.instrument import stats
from swingbot.core.backtesting.screen import diagnostics, verdict
from swingbot.core.backtesting.screen.context import ContextData
from swingbot.core.backtesting.screen.ideas import Idea
from tests.backtesting.screen.helpers import frame

N_BARS = 800
SHOCKS = (300, 450, 451, 452, 460, 600)    # 300 falls in 2010, before the event window
DIP = 460                                  # SPY closes far lower here: r5 < 0 on that shock day


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    monkeypatch.setattr(verdict, "decide", functools.partial(verdict.decide, n_resamples=300))


def _calendar() -> pd.DataFrame:
    closes = 100.0 + 0.1 * np.arange(N_BARS)
    closes[DIP] = 90.0
    return frame(closes, start="2009-06-01")


def _shock_events(df, context):
    days = context["TLT"].index[list(SHOCKS)]
    return pd.Series(df.index.isin(days), index=df.index, name="fake_ctx")


def _idea():
    return Idea(name="fake_ctx", events=_shock_events, time_cap_bars=10,
                params={"series": "TLT", "lookback": 5, "window": 252, "z": 2.0,
                        "side": "long"},
                summary="s", source="src", context=("TLT",))


def _data() -> ContextData:
    cal = _calendar()
    tlt = frame(50.0 + 0.01 * np.arange(N_BARS), start="2009-06-01")
    record = {"ticker": "TLT", "rows": N_BARS, "first": "2009-06-01",
              "last": cal.index[-1].strftime("%Y-%m-%d"), "fetched": "2026-10-18",
              "sha256": "ab" * 32}
    return ContextData(frames={"TLT": tlt}, calendar=cal, records={"TLT": record})


def _entry(pos: int) -> str:
    return _calendar().index[pos + 1].strftime("%Y-%m-%d")


def _row(ticker, signal_pos, r_event, r_null):
    return {"ticker": ticker, "entry_date": _entry(signal_pos), "exit_date": _entry(signal_pos + 5),
            "r_event": r_event, "r_null": r_null, "outcome": "timeout"}


def _events():
    """d = +0.5, +0.3 (episode 450-452), -0.2 (episode 460), +0.1 (episode 600),
    0.0 on a non-shock signal day (470): N = 5, mean d = +0.14."""
    return [_row("AAA", 450, 0.6, 0.1), _row("BBB", 450, 0.4, 0.1),
            _row("AAA", 460, -0.1, 0.1), _row("AAA", 600, 0.3, 0.2),
            _row("BBB", 470, 0.2, 0.2)]


def _window():
    return {"event_start": "2011-01-01", "event_end": "2019-12-31"}


# --- signal days and episodes ---------------------------------------------

def test_a_signal_day_is_the_session_before_the_entry():
    sessions = pd.bdate_range("2011-03-01", "2011-03-10")
    out = diagnostics.signal_days(["2011-03-07", "2011-03-02"], sessions)
    assert out == [pd.Timestamp("2011-03-04"), pd.Timestamp("2011-03-01")]   # Monday -> Friday


def test_an_entry_off_the_calendar_maps_to_the_last_session_before_it():
    sessions = pd.bdate_range("2011-03-01", "2011-03-10")
    assert diagnostics.signal_days(["2011-03-05"], sessions) == [pd.Timestamp("2011-03-04")]


def test_an_entry_on_the_first_session_has_no_signal_day():
    sessions = pd.bdate_range("2011-03-01", "2011-03-10")
    assert pd.isna(diagnostics.signal_days(["2011-03-01"], sessions)[0])


def test_episodes_split_on_a_gap_of_more_than_five_sessions():
    sessions = pd.bdate_range("2011-01-03", periods=100)
    days = sessions[[10, 11, 12, 18, 30, 35]]
    out = diagnostics.episodes(days, sessions)
    assert [list(run) for run in out] == [list(sessions[[10, 11, 12]]), [sessions[18]],
                                          list(sessions[[30, 35]])]   # 30 -> 35 is exactly 5
    assert diagnostics.EPISODE_GAP == 5


def test_no_shock_day_is_no_episode():
    assert diagnostics.episodes(pd.DatetimeIndex([]), pd.bdate_range("2011-01-03", periods=5)) == []


def test_shock_days_are_the_calendar_dates_the_idea_fires_inside_the_event_window():
    data = _data()
    out = diagnostics.shock_days(_idea(), data, **_window())
    assert list(out) == list(data.calendar.index[[450, 451, 452, 460, 600]])   # 300 is 2010


# --- screen-family q and scope ----------------------------------------------

def test_the_screen_family_q_counts_screen_rows_only():
    rows = [{"id": "v139-arm-d", "instrument": "v1", "p": 0.001},
            {"id": "v139-arm-e", "instrument": "v1", "p": 0.9},
            {"id": "screen-a", "instrument": "screen-v1", "p": 0.04},
            {"id": "screen-b", "instrument": "screen-v1", "p": None}]
    row = {"id": "screen-new", "instrument": "screen-v1", "p": 0.03}
    family = diagnostics.screen_family_q(rows, row, "screen-v1")
    whole = stats.ledger_qvalues(rows + [row])["screen-new"]
    assert family == pytest.approx(stats.bh_qvalues([0.04, 0.03])[1])
    assert family == pytest.approx(0.04)
    assert whole == pytest.approx(0.04 * 4 / 3)
    assert family != pytest.approx(whole)


def test_the_screen_family_q_is_none_without_a_p():
    row = {"id": "screen-new", "instrument": "screen-v1", "p": None}
    assert diagnostics.screen_family_q([], row, "screen-v1") is None


def test_the_scope_sentence_closes_the_frozen_definition_only():
    text = diagnostics.scope_sentence(_idea())
    for needle in ("TLT 5-day return z >= +2.0", "trailing 252 values", "long only",
                   "fixed 10-bar race", "closes exactly this frozen definition",
                   "not intermarket analysis", "not a slow-regime test",
                   "not a bearish or longer-horizon variant"):
        assert needle in text, needle


def test_the_scope_sentence_reads_a_negative_threshold_as_at_most():
    idea = Idea(name="fake_drop", events=_shock_events, time_cap_bars=10,
                params={"series": "UUP", "lookback": 5, "window": 252, "z": -2.0,
                        "side": "long"}, summary="s", source="src", context=("UUP",))
    assert "UUP 5-day return z <= -2.0" in diagnostics.scope_sentence(idea)


# --- compute ----------------------------------------------------------------

def test_the_effective_sample_counts_shock_days_episodes_and_weeks():
    data = _data()
    sample = diagnostics.compute(_idea(), _events(), None, data, **_window())["sample"]
    assert (sample["n"], sample["shock_days"], sample["episodes"]) == (5, 5, 3)
    assert sample["weeks"] == 4                       # entries 451 (twice), 461, 471, 601
    shocks = Counter(data.calendar.index[p].year for p in (450, 451, 452, 460, 600))
    kept = Counter(int(row["entry_date"][:4]) for row in _events())
    assert sample["per_year"] == {year: (shocks.get(year, 0), kept.get(year, 0))
                                  for year in verdict.YEARS}


def test_the_null_overlap_recomputes_delta_on_the_restricted_pairs():
    restricted = [{"entry_date": _entry(450), "r_event": 0.6, "r_null": 0.3},
                  {"entry_date": _entry(600), "r_event": 0.3, "r_null": 0.3}]
    out = diagnostics.compute(_idea(), _events(), restricted, _data(), **_window())["overlap"]
    assert out["cap"] == 10 and out["n"] == 5
    assert out["official"] == pytest.approx(0.14)
    assert out["restricted"].n == 2
    assert out["restricted"].delta_exp_r == pytest.approx(0.15)


def test_no_restricted_pass_reports_none():
    out = diagnostics.compute(_idea(), _events(), None, _data(), **_window())["overlap"]
    assert out["restricted"] is None


def test_the_selloff_split_reads_spy_r5_at_each_signal_day():
    out = diagnostics.compute(_idea(), _events(), None, _data(), **_window())["selloff"]
    assert (out["shock_down"], out["shock_up"]) == (1, 4)
    assert out["down"].n == 1 and out["down"].delta_exp_r == pytest.approx(-0.2)
    assert out["up"].n == 4 and out["up"].delta_exp_r == pytest.approx(0.225)
    assert out["undefined"] == 0
    assert out["shock_mean"] is not None


def test_concentration_sorts_episode_contributions_largest_first():
    out = diagnostics.compute(_idea(), _events(), None, _data(), **_window())["concentration"]
    cal = _calendar().index
    labels = [f"{cal[450]:%Y-%m-%d}..{cal[452]:%Y-%m-%d}", f"{cal[600]:%Y-%m-%d}",
              f"{cal[460]:%Y-%m-%d}"]
    assert [row[0] for row in out["rows"]] == labels
    assert [row[1] for row in out["rows"]] == [2, 1, 1]
    assert [row[2] for row in out["rows"]] == pytest.approx([0.16, 0.02, -0.04])
    assert out["unmatched"] == 1                      # the signal day 470 is no shock day
    assert out["delta"] == pytest.approx(0.14)


def test_every_decide_goes_through_the_module_attribute(monkeypatch):
    calls = []
    real = verdict.decide

    def spy(events, **kw):
        calls.append(len(list(events)))
        return real(events, n_resamples=200)

    monkeypatch.setattr(verdict, "decide", spy)
    restricted = [{"entry_date": _entry(450), "r_event": 0.6, "r_null": 0.3}]
    diagnostics.compute(_idea(), _events(), restricted, _data(), **_window())
    assert sorted(calls) == [1, 1, 4]                 # restricted, selloff down, selloff up


def test_compute_never_mutates_the_event_rows():
    events = _events()
    snapshot = [dict(row) for row in events]
    diagnostics.compute(_idea(), events, None, _data(), **_window())
    assert events == snapshot


# --- render -------------------------------------------------------------------

def _rendered(restricted=None, screen_q=0.0421):
    data = _data()
    diag = diagnostics.compute(_idea(), _events(), restricted, data, **_window())
    return diagnostics.render(diag, data, context_start="2009-06-01",
                              window_start="2010-01-01", screen_q=screen_q,
                              scope=diagnostics.scope_sentence(_idea()))


def test_render_opens_with_the_never_gating_heading():
    lines = _rendered()
    assert lines[0] == "## Intermarket diagnostics (printed, never gating)"
    assert all(isinstance(line, str) for line in lines)


def test_render_prints_all_six_diagnostics():
    text = "\n".join(_rendered())
    for needle in ("### 1. Effective sample", "### 2. Null overlap",
                   "### 3. SPY selloff split", "### 4. Concentration by shock episode",
                   "### 5. Multiple comparisons", "### 6. Scope",
                   "5 shock days in 3 episodes", "4 distinct ISO entry weeks",
                   "undercovers", "Restricted null not run",
                   "| < 0 | 1 |", "| >= 0 | 4 |", "mean-reversion effect",
                   "BH q = 0.0421 across the `screen-v1` family",
                   "closes exactly this frozen definition"):
        assert needle in text, needle


def test_render_records_both_starts_and_every_context_file():
    text = "\n".join(_rendered())
    assert "loaded from 2009-06-01" in text and "stock window starts 2010-01-01" in text
    assert "| TLT | 800 | 2009-06-01 |" in text
    assert "ab" * 32 in text and "2026-10-18" in text


def test_render_prints_the_restricted_delta_when_the_pass_ran():
    restricted = [{"entry_date": _entry(450), "r_event": 0.6, "r_null": 0.3},
                  {"entry_date": _entry(600), "r_event": 0.3, "r_null": 0.3}]
    text = "\n".join(_rendered(restricted))
    assert "at least 10 sessions from any shock day" in text
    assert "ΔExpR +0.1500R" in text and "N = 2" in text


def test_render_prints_n_a_without_a_screen_q():
    assert "BH q = n/a across" in "\n".join(_rendered(screen_q=None))


def test_empty_events_still_report_context_shocks_without_an_estimate():
    data = _data()
    out = diagnostics.compute(_idea(), [], None, data, **_window())
    assert out["sample"]["n"] == 0 and out["sample"]["weeks"] == 0
    assert out["sample"]["shock_days"] == 5
    assert out["overlap"]["official"] is None
    assert out["selloff"]["down"] is None and out["selloff"]["up"] is None
    assert out["concentration"] == {"rows": [], "unmatched": 0, "delta": None}
    lines = diagnostics.render(out, data, context_start="2009-06-01",
                               window_start="2010-01-01", screen_q=None, scope="scope")
    assert "Official ΔExpR n/aR over N = 0." in "\n".join(lines)


def test_missing_signal_or_warmup_return_stays_undefined_and_unmatched():
    first = _row("AAA", 0, 0.5, 0.1)
    first["entry_date"] = "2009-06-01"
    events = [first, _row("BBB", 1, 0.2, 0.1)]
    out = diagnostics.compute(_idea(), events, None, _data(), **_window())
    assert out["selloff"]["undefined"] == 2
    assert out["selloff"]["down"] is None and out["selloff"]["up"] is None
    assert out["concentration"]["rows"] == []
    assert out["concentration"]["unmatched"] == 2


def test_empty_restricted_pass_reports_zero_pairs_instead_of_not_run():
    out = diagnostics.compute(_idea(), _events(), [], _data(), **_window())
    result = out["overlap"]["restricted"]
    assert isinstance(result, verdict.Verdict)
    assert result.n == 0
    assert result.delta_exp_r is None and result.ci_low is None and result.ci_high is None
    text = "\n".join(_rendered(restricted=[]))
    assert "Restricted null not run" not in text
    assert "at least 10 sessions from any shock day" in text
    assert "N = 0" in text and "interval n/aR to n/aR" in text
