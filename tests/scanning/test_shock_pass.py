"""v209: shock_scan.run_shock_pass and current_label -- the stepped pass."""
import inspect
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.scanning import fetch, shock_scan

UTC = timezone.utc
D0 = date(2026, 11, 5)                                  # Thursday, EST (UTC-5)
NOW = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)          # 10:00 ET, 30 min after the open
PRE_MARKET = datetime(2026, 11, 5, 13, 0, tzinfo=UTC)   # 08:00 ET
SECTORS = {"AAA": "Tech", "BBB": "Tech", "CCC": "Tech"}
CRASH_QUOTES = {"AAA": 94.0, "BBB": 94.0, "CCC": 94.0, "SPY": 490.0}   # -3 ATR each


def _frame(close=100.0, partial=None, n=30):
    idx = pd.bdate_range(end=pd.Timestamp(D0), periods=n)
    df = pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0,
                       "Close": close, "Volume": 1e6}, index=idx)
    if partial is not None:
        df.iloc[-1, df.columns.get_loc("Close")] = partial
    return df


def _crash_frames():
    return {t: _frame(partial=95.0) for t in SECTORS} | {"SPY": _frame(close=500.0)}


class _Repo:
    def __init__(self, state=None, fail=False):
        self.state, self.latest, self.fail, self.recorded = state, None, fail, []

    def current_state(self, *, conn=None):
        if self.fail:
            raise RuntimeError("db down")
        return self.state

    def latest_reading(self, *, conn=None):
        if self.fail:
            raise RuntimeError("db down")
        return self.latest

    def record(self, reading, state, *, state_after, notice_event=None, conn=None):
        self.recorded.append((reading, state, state_after))
        self.latest = {**reading, "id": len(self.recorded), "state_after": state_after}
        self.state = {"label": state_after, "doc": {"state": state}}
        return len(self.recorded)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "shadow")
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(config, "SHOCK_MIN_NAMES", 2)
    monkeypatch.setattr(shock_scan.asset_class, "classify",
                        lambda t: "etf" if t in ("SPY", "QQQ") else "equity")
    monkeypatch.setattr(shock_scan.tape, "read_tape", lambda symbols: {})
    # The pass never fetches a quote (LONG issuing unchanged, (b)): any call fails the test.
    monkeypatch.setattr(fetch, "_fetch_live_prices",
                        lambda tickers, progress=None: pytest.fail("the shock pass fetched quotes"))


def _pass(repo, *, step=True, now=NOW, quotes=CRASH_QUOTES, quotes_at=None):
    return shock_scan.run_shock_pass(step_shock=step, frames=_crash_frames(), live_prices=quotes,
                                     sector_of=SECTORS, quotes_at=quotes_at or now, now=now,
                                     repo=repo)


def _without_spy():
    return {k: v for k, v in CRASH_QUOTES.items() if k != "SPY"}


def test_off_returns_none_and_never_touches_the_repo(monkeypatch):
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "off")
    repo = _Repo(fail=True)
    assert _pass(repo) is None and repo.recorded == []
    assert shock_scan.current_label(repo=repo) is None


@pytest.mark.parametrize("step,now", [(False, NOW), (True, PRE_MARKET)])
def test_an_unstepped_pass_reads_the_label_and_writes_nothing(step, now):
    repo = _Repo(state={"label": "SHOCK", "doc": {}})
    assert _pass(repo, step=step, now=now, quotes=_without_spy()) == "SHOCK"
    assert repo.recorded == []


def test_two_stepped_crash_readings_enter_shock_and_record_each():
    repo = _Repo()
    assert _pass(repo) == "NORMAL"                                  # first qualifying reading
    reading, state, after = repo.recorded[0]
    assert after == "NORMAL" == state["label"]
    assert reading["n_names"] == 3 and reading["breadth_frac"] == pytest.approx(1.0)
    assert (reading["sectors_down"], reading["sectors_total"]) == (1, 1)
    assert reading["depth_frac"] == pytest.approx(1.0)
    assert reading["spy_last"] == 490.0 and reading["spy_prev_close"] == 500.0
    assert _pass(repo, now=NOW + timedelta(minutes=15)) == "SHOCK"
    assert len(repo.recorded) == 2 and repo.recorded[1][2] == "SHOCK"


def test_the_previous_reading_feeds_breadth_speed_within_the_session():
    repo = _Repo()
    _pass(repo)
    _pass(repo, now=NOW + timedelta(minutes=15))
    assert repo.recorded[0][0]["breadth_speed"] is None
    assert repo.recorded[1][0]["breadth_speed"] == pytest.approx(0.0)


def test_stale_quotes_make_an_insufficient_reading_that_holds_the_state():
    repo = _Repo()
    label = _pass(repo, quotes_at=NOW - timedelta(seconds=301))
    reading = repo.recorded[0][0]
    assert label == "NORMAL" and reading["insufficient"] is True and reading["n_names"] == 0
    assert reading["spy_last"] is None                    # stale SPY is absent too, never re-quoted


def test_a_missing_spy_quote_records_the_reading_from_breadth_and_vix():
    repo = _Repo()
    assert _pass(repo, quotes=_without_spy()) == "NORMAL"
    reading = repo.recorded[0][0]
    assert reading["n_names"] == 3 and reading["breadth_frac"] == pytest.approx(1.0)
    assert reading["insufficient"] is False
    assert (reading["spy_last"], reading["spy_atr_move"], reading["spy_retrace"]) == (None, None, None)


def test_a_missing_spy_quote_still_enters_shock_on_breadth():
    repo = _Repo()
    _pass(repo, quotes=_without_spy())
    assert _pass(repo, now=NOW + timedelta(minutes=15), quotes=_without_spy()) == "SHOCK"


def test_the_spy_df_argument_wins_over_frames():
    repo = _Repo()
    shock_scan.run_shock_pass(step_shock=True, frames=_crash_frames(), live_prices=CRASH_QUOTES,
                              sector_of=SECTORS, quotes_at=NOW, now=NOW, repo=repo,
                              spy_df=_frame(close=520.0))
    assert repo.recorded[0][0]["spy_prev_close"] == 520.0


def test_a_failing_step_falls_back_to_the_stored_label(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise ValueError("bad reading")
    monkeypatch.setattr(shock_scan.shock, "measure", boom)
    repo = _Repo(state={"label": "RECOVERY", "doc": {}})
    assert _pass(repo) == "RECOVERY" and repo.recorded == []
    assert any(getattr(r, "swallowed_tag", "") == "scan.shock.pass" for r in caplog.records)


def test_a_dead_store_never_fails_the_pass():
    assert _pass(_Repo(fail=True)) is None


BRANCHES = {
    "off": dict(mode="off"),
    "unstepped": dict(step=False),
    "pre_market": dict(now=PRE_MARKET),
    "stepped": dict(),
    "stale_quotes": dict(quotes_at=NOW - timedelta(seconds=301)),
    "spy_missing": dict(quotes=_without_spy()),
    "no_quotes": dict(quotes={}),
    "dead_store": dict(fail=True),
}


@pytest.mark.parametrize("branch", sorted(BRANCHES))
def test_no_branch_of_the_pass_fetches_a_quote(monkeypatch, branch):
    over = dict(BRANCHES[branch])
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", over.pop("mode", "shadow"))
    _pass(_Repo(fail=over.pop("fail", False)), **over)    # the autouse stub fails on any fetch


def test_shock_scan_has_no_quote_fetch_in_its_source():
    src = inspect.getsource(shock_scan)
    assert "_fetch_live_prices(" not in src and "import fetch" not in src
    assert not hasattr(shock_scan, "fetch")


def test_current_label_defaults_to_normal_and_survives_a_db_failure():
    assert shock_scan.current_label(repo=_Repo()) == "NORMAL"
    assert shock_scan.current_label(repo=_Repo(state={"label": "SHOCK", "doc": {}})) == "SHOCK"
    assert shock_scan.current_label(repo=_Repo(state={"label": "CALM", "doc": {}})) is None
    assert shock_scan.current_label(repo=_Repo(fail=True)) is None
