"""v239 V239-8: the regime pass -- compute-or-read D, insert once, notice from the winner.

The replay fixture (V239-2b) gives real bars: labelled after the 11-19 close,
D = 11-20 is CORRECTION with stress (the verified Yahoo replay)."""
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.db.repositories import market_regime as mr
from swingbot.core.market import bear_regime as br
from swingbot.core.scanning import regime_scan as rs

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "regime" / "spy_vix_replay.csv"
AFTER_CLOSE = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)   # 17:00 ET Thu
INTRADAY = datetime(2026, 11, 20, 16, 0, tzinfo=timezone.utc)      # 11:00 ET Fri
S, D = date(2026, 11, 19), date(2026, 11, 20)


def _replay():
    raw = pd.read_csv(FIXTURE, parse_dates=["Date"], index_col="Date")
    spy = raw.rename(columns={"spy_high": "High", "spy_close": "Close"})[["High", "Close"]]
    vix = raw[["vix_close"]].rename(columns={"vix_close": "Close"}).dropna()
    return spy, vix


SPY, VIX = _replay()


def _fetcher(spy=SPY, vix=VIX, calls=None, fail=()):
    def fetch(symbol):
        if calls is not None:
            calls.append(symbol)
        if symbol in fail:
            raise ValueError(f"no data for {symbol}")
        df = (spy if symbol == br.SPY else vix).copy()
        df.attrs["source"] = "alpaca" if symbol == br.SPY else "yfinance"
        return df
    return fetch


class _Repo:
    """In-memory MarketRegimeRepository: rows by session, and what it enqueued."""

    def __init__(self, rows=(), winner=None, fail=False):
        self.rows = {row["session_date"]: row for row in rows}
        self.inserted, self.events, self.winner, self.fail = [], [], winner, fail

    def day(self, session_date, *, conn=None):
        if self.fail:
            raise RuntimeError("store down")
        return self.rows.get(session_date)

    def recent(self, limit=60, *, conn=None):
        return [self.rows[key] for key in sorted(self.rows)][-limit:]

    def insert_once(self, row, *, notice_event=None, conn=None):
        if self.winner is not None:            # another process inserted first
            self.rows[row["session_date"]] = self.winner
            return False
        self.rows[row["session_date"]] = row
        self.inserted.append(row)
        self.events.append(notice_event)
        return True


class _Broken:
    def __iter__(self):
        raise RuntimeError("store down")


def _row(day, state, stress=False):
    regime_day = br.RegimeDay(session_date=day, last_bar_date=day - timedelta(days=1),
                              state=state, stress=stress)
    return {**regime_day.to_row(), "computed_at": AFTER_CLOSE}


def _prior(*states, end=S):
    """Stored rows, one per weekday ending at `end`, oldest first."""
    days = pd.bdate_range(end=end, periods=len(states)).date
    return [_row(day, state) for day, state in zip(days, states)]


def _labels_as(monkeypatch, **fields):
    day = br.RegimeDay(session_date=D, last_bar_date=S,
                       **{"state": br.CORRECTION, "stress": False, **fields})
    monkeypatch.setattr(br, "classify", lambda *args, **kwargs: day)
    return day


def _run(repo, now=AFTER_CLOSE, fetch=None, plans=(), trades=()):
    return rs.regime_for_pass(now=now, repo=repo, fetch=fetch or _fetcher(),
                              plans=list(plans), trades=list(trades))


def _tagged(caplog, tag):
    return any(getattr(record, "swallowed_tag", "") == tag for record in caplog.records)


@pytest.fixture(autouse=True)
def _shadow(monkeypatch):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", "shadow")


def test_constants_and_the_db_layer_restates_the_classifier_row():
    assert (rs.FETCH_PERIOD, rs.PRIOR_SESSIONS) == ("2y", 60)
    assert mr.COLUMNS == br.ROW_COLUMNS
    assert mr.STATES == br.STATES


@pytest.mark.parametrize("mode", ["off", "bogus"])
def test_off_touches_neither_the_store_nor_the_network(monkeypatch, mode):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", mode)
    calls, touched = [], []
    monkeypatch.setattr(rs, "market_regime_repo", lambda: touched.append("repo"))
    assert rs.regime_for_pass(now=AFTER_CLOSE, fetch=_fetcher(calls=calls)) is None
    assert calls == [] and touched == []


def test_live_behaves_like_shadow(monkeypatch):
    monkeypatch.setattr(config, "BEAR_REGIME_MODE", "live")
    assert _run(_Repo()).state == br.CORRECTION


def test_a_stored_row_is_read_back_without_a_fetch():
    calls, repo = [], _Repo([_row(D, br.BEAR)])
    day = _run(repo, fetch=_fetcher(calls=calls))
    assert (day.session_date, day.state) == (D, br.BEAR)
    assert calls == [] and repo.inserted == []


def test_no_row_computes_d_from_both_feeds_and_stores_it_once():
    calls, repo = [], _Repo()
    day = _run(repo, fetch=_fetcher(calls=calls))
    assert sorted(calls) == ["SPY", "^VIX"]
    assert (day.session_date, day.last_bar_date, day.state, day.stress) == (
        D, S, br.CORRECTION, True)
    assert (day.spy_provider, day.vix_provider) == ("alpaca", "yfinance")
    assert repo.inserted == [{**day.to_row(), "computed_at": AFTER_CLOSE}]
    assert _run(repo, fetch=_fetcher(calls=calls)) == day      # the next pass reads it
    assert len(calls) == 2 and len(repo.inserted) == 1


def test_a_partial_bar_and_later_bars_are_cut_before_classifying():
    day = _run(_Repo(), now=INTRADAY)                 # the frames carry the partial 11-20 bar
    hand = br.classify(SPY.loc[:"2026-11-19"], VIX.loc[:"2026-11-19"], last_session=S,
                       session_date=D, spy_provider="alpaca", vix_provider="yfinance")
    assert day == hand


def test_a_stale_spy_label_is_stamped_but_not_stored_so_the_next_pass_retries():
    repo = _Repo()
    stale = _run(repo, fetch=_fetcher(spy=SPY.loc[:"2026-11-18"]))
    assert (stale.state, stale.unknown_reason) == (br.UNKNOWN, br.REASON_STALE)
    assert repo.inserted == []
    assert _run(repo).state == br.CORRECTION and len(repo.inserted) == 1


def test_a_short_history_unknown_is_stored():
    repo = _Repo()
    day = _run(repo, fetch=_fetcher(spy=SPY.loc[:"2026-11-19"].tail(100)))
    assert (day.state, day.unknown_reason) == (br.UNKNOWN, br.REASON_SHORT)
    assert len(repo.inserted) == 1


def test_a_failed_spy_fetch_is_a_stale_unknown_and_never_raises(caplog):
    repo = _Repo()
    with caplog.at_level(logging.WARNING):
        day = _run(repo, fetch=_fetcher(fail=("SPY",)))
    assert (day.state, day.unknown_reason) == (br.UNKNOWN, br.REASON_STALE)
    assert repo.inserted == [] and _tagged(caplog, "scan.regime.fetch")


def test_a_failed_vix_fetch_stores_a_day_without_stress():
    repo = _Repo()
    day = _run(repo, fetch=_fetcher(fail=("^VIX",)))
    assert (day.state, day.stress, day.vix_provider) == (br.CORRECTION, None, None)
    assert len(repo.inserted) == 1


def test_a_store_failure_returns_none_and_never_raises(caplog):
    with caplog.at_level(logging.WARNING):
        assert _run(_Repo(fail=True)) is None
    assert _tagged(caplog, "scan.regime.pass")


def test_a_lost_race_returns_the_winners_row():
    winner = _row(D, br.BEAR)
    assert _run(_Repo(winner=winner)) == br.RegimeDay.from_row(winner)


def test_a_single_new_session_is_flicker_stored_without_a_notice(monkeypatch):
    _labels_as(monkeypatch)
    repo = _Repo(_prior(br.NORMAL, br.NORMAL, br.NORMAL))
    _run(repo)
    assert len(repo.inserted) == 1 and repo.events == [None]


def test_the_confirming_session_enqueues_one_notice_with_the_book(monkeypatch):
    _labels_as(monkeypatch)
    repo = _Repo(_prior(br.NORMAL, br.NORMAL, br.CORRECTION))
    plans = [SimpleNamespace(ticker="AAPL", status="PENDING", direction="bullish",
                             trigger_price=101.5, entry_context={"bear_regime": "NORMAL"})]
    trades = [{"direction": "bullish"}, {"direction": "bullish"}, {"direction": "bearish"}]
    _run(repo, plans=plans, trades=trades)
    (event,) = repo.events
    payload = event["payload"]
    assert (event["kind"], event["transition_id"]) == ("bear_regime", f"market_regime:{D}")
    assert (payload["kind"], payload["old_label"], payload["new_label"]) == (
        "transition", "Normal", "Correction")
    assert payload["open_longs"] == 2 and payload["gap_sessions"] == 1
    assert payload["unfilled"] == [{"ticker": "AAPL", "entry": 101.5}]


def test_a_pullback_day_notifies_without_a_transition(monkeypatch):
    _labels_as(monkeypatch, pullback_trigger=True)
    repo = _Repo(_prior(br.CORRECTION, br.CORRECTION))
    _run(repo)
    assert repo.events[0]["payload"]["kind"] == "pullback"


def test_a_gap_is_counted_in_nyse_sessions(monkeypatch):
    _labels_as(monkeypatch)
    repo = _Repo(_prior(br.NORMAL, br.NORMAL, br.CORRECTION, end=date(2026, 11, 6)))
    _run(repo)
    assert repo.events[0]["payload"]["gap_sessions"] == 10     # 11-09..11-13, 11-16..11-20


def test_a_notice_that_cannot_be_built_never_costs_the_row(monkeypatch, caplog):
    _labels_as(monkeypatch)
    monkeypatch.setattr(rs.regime_notices, "notice_payload", lambda *a, **k: 1 / 0)
    repo = _Repo(_prior(br.NORMAL, br.NORMAL, br.CORRECTION))
    with caplog.at_level(logging.WARNING):
        _run(repo)
    assert len(repo.inserted) == 1 and repo.events == [None]
    assert _tagged(caplog, "scan.regime.notice")


def test_unreadable_plans_and_trades_read_as_unavailable(monkeypatch):
    _labels_as(monkeypatch)
    repo = _Repo(_prior(br.NORMAL, br.NORMAL, br.CORRECTION))
    rs.regime_for_pass(now=AFTER_CLOSE, repo=repo, fetch=_fetcher(), plans=_Broken(),
                       trades=_Broken())
    payload = repo.events[0]["payload"]
    assert (payload["open_longs"], payload["unfilled"]) == (None, None)
