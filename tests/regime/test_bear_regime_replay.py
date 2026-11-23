"""v239 V239-2b: the spec's replay of the 2026 decline, on real bars.

Fixture: tests/fixtures/regime/spy_vix_replay.csv, adjusted SPY high/close and
^VIX close per SPY session, 2025-08-01 -> 2026-11-20, cut from
data/backtest_cache_regime/ (scripts/data/fetch_regime_data.py, V239-1).
vix_close is blank where ^VIX had no bar that session: never filled.

Convention: D is labelled from s, the prior completed SPY session. Each D
is labelled from the full frames; classify cuts them to s itself.

The original spec's continuous correction from D=10-22 and stress only on
D=11-17..11-20 disagreed with the manifest-verified Yahoo cache. The partner
authorized correcting these replay dates on 2026-11-23, keeping all frozen
classifier rules. The exact raw daily labels below include intervening NORMAL
days; they deliberately apply no episode smoothing."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from swingbot.core.market import bear_regime as br

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "regime" / "spy_vix_replay.csv"
FIRST_D, LAST_D, NEXT_D = date(2026, 10, 22), date(2026, 11, 20), date(2026, 11, 23)
CORRECTION_DAYS = {date.fromisoformat(value) for value in (
    "2026-10-23", "2026-10-26", "2026-10-27",
    "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-06",
    "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13",
    "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20",
    "2026-11-23",
)}
STRESS_DAYS = {date(2026, 11, day) for day in (6, 9, 18, 20, 23)}


@pytest.fixture(scope="module")
def labels() -> dict:
    raw = pd.read_csv(FIXTURE, parse_dates=["Date"], index_col="Date")
    spy = raw.rename(columns={"spy_high": "High", "spy_close": "Close"})[["High", "Close"]]
    vix = raw[["vix_close"]].rename(columns={"vix_close": "Close"}).dropna()
    sessions = [ts.date() for ts in spy.index]
    out = {}
    for s, d in zip(sessions, sessions[1:] + [NEXT_D]):
        if d >= date(2026, 10, 15):
            out[d] = br.classify(spy, vix, last_session=s, session_date=d,
                                 spy_provider="yfinance", vix_provider="yfinance")
    return out


def test_fixture_covers_the_window_with_enough_history():
    raw = pd.read_csv(FIXTURE, parse_dates=["Date"], index_col="Date")
    assert list(raw.columns) == ["spy_high", "spy_close", "vix_close"]
    assert raw.index[-1] == pd.Timestamp("2026-11-20")
    assert (raw.index <= pd.Timestamp("2026-10-21")).sum() >= br.MIN_BARS + 40


def test_raw_daily_states_match_the_verified_replay(labels):
    assert len(labels) == 28
    assert set(labels) >= CORRECTION_DAYS
    expected = {d: br.CORRECTION if d in CORRECTION_DAYS else br.NORMAL for d in labels}
    assert {d: day.state for d, day in labels.items()} == expected


def test_never_bear_through_the_decline(labels):
    assert all(day.state != br.BEAR for d, day in labels.items() if d >= FIRST_D)
    last = labels[NEXT_D]                                # s = 11-20, SPY at its low
    assert last.sma200 > last.sma200_lag20              # SMA200 still rising
    assert last.spy_close < last.sma200                 # under SMA200, yet not BEAR


def test_stress_dates_match_the_verified_replay(labels):
    assert {d for d, day in labels.items() if day.stress} == STRESS_DAYS
    assert all(day.stress is not None for day in labels.values())


def test_every_day_is_a_full_reading_from_an_earlier_bar(labels):
    for d, day in labels.items():
        assert day.state != br.UNKNOWN, (d, day.unknown_reason)
        assert day.last_bar_date < d


def test_real_bar_labels_equal_frames_truncated_at_s(labels):
    raw = pd.read_csv(FIXTURE, parse_dates=["Date"], index_col="Date")
    for d, full in labels.items():
        past = raw.loc[:pd.Timestamp(full.last_bar_date)]
        spy = past.rename(columns={"spy_high": "High", "spy_close": "Close"})[["High", "Close"]]
        vix = past[["vix_close"]].rename(columns={"vix_close": "Close"}).dropna()
        assert br.classify(spy, vix, last_session=full.last_bar_date, session_date=d,
                           spy_provider="yfinance", vix_provider="yfinance") == full
