"""v208 V208-6: the benchmarks refresher step -- once-a-day full refresh, 5-minute intraday, never fails."""
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot.core.infra import swallowed as sw
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared.kinds import Asker
from swingbot.refresher import benchmarks as step
from swingbot.refresher import loop, quotes
from swingbot.refresher.symbols import SymbolSet

UTC = timezone.utc
SYMBOLS = ("SPY", "QQQ", "^IXIC", "^DJI")
SINCE = date(2026, 10, 28)
AFTER_CLOSE = datetime(2026, 11, 4, 22, 0, tzinfo=UTC)    # Wed 17:00 ET
IN_SESSION = datetime(2026, 11, 4, 15, 0, tzinfo=UTC)     # Wed 10:00 ET
ALL_SESSIONS = [date(2026, 10, 28), date(2026, 10, 29), date(2026, 10, 30),
                date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)]


class FakeBars:
    def __init__(self):
        self.rows = {}
        self.upserts = 0

    def upsert_bars(self, rows, conn=None):
        self.upserts += 1
        for row in rows:
            self.rows[(row["symbol"], row["session"])] = dict(row)
        return len(rows)

    def list_range(self, symbols, start, end, conn=None):
        return [r for (s, d), r in sorted(self.rows.items()) if s in symbols and start <= d <= end]


class FakeRefresh:
    def __init__(self, done=None):
        self.done = dict(done or {})

    def full_refreshed_on(self, symbol, conn=None):
        return self.done.get(symbol)

    def mark_full_refresh(self, symbol, day, conn=None):
        self.done[symbol] = day


def _bar(symbol, day, *, final=True, close=100.0):
    return {"symbol": symbol, "session": day, "close": close, "adj_close": close, "day_pct": 0.01,
            "source_symbol": symbol, "final": final, "as_of": AFTER_CLOSE}


@pytest.fixture
def env(monkeypatch):
    step.reset_state()
    state = {"bars": FakeBars(), "refresh": FakeRefresh(), "history": [], "prices": [],
             "through": None, "asker": []}

    def history(symbol, start, *, sessions, final_through, now, fetch=None):
        state["history"].append((symbol, start, list(sessions), final_through))
        state["asker"].append(router.current_asker())
        through = state["through"] or final_through
        return [_bar(symbol, d) for d in sessions if d <= through]

    def prices(symbols):
        state["prices"].append(tuple(symbols))
        return {s: 101.0 for s in symbols}

    monkeypatch.setattr(step, "benchmark_bars_repo", lambda: state["bars"])
    monkeypatch.setattr(step, "benchmark_refresh_repo", lambda: state["refresh"])
    monkeypatch.setattr(step, "live_since", lambda: SINCE)
    monkeypatch.setattr(step.mb, "history_with_fallback", history)
    monkeypatch.setattr(step.mb, "latest_benchmark_prices", prices)
    yield state
    step.reset_state()


def _ctx(now, state="closed", scan_running=False):
    return loop.CycleContext(now, state, SymbolSet((), ()), [], [], scan_running,
                             loop.CycleReport(state, 30.0))


def test_the_step_runs_last_right_after_the_fx_snap():
    assert loop.STEPS[-1] is step.benchmarks_step
    assert loop.STEPS.index(step.benchmarks_step) == loop.STEPS.index(quotes.fx_snap_step) + 1


def test_a_running_scan_skips_the_step(env):
    step.benchmarks_step(_ctx(AFTER_CLOSE, scan_running=True))
    assert env["history"] == [] and env["bars"].rows == {}


def test_no_equity_yet_writes_nothing(env, monkeypatch):
    monkeypatch.setattr(step, "live_since", lambda: None)
    step.benchmarks_step(_ctx(AFTER_CLOSE))
    assert env["history"] == []


def test_a_restart_after_days_down_catches_up_every_session_in_one_refresh(env):
    env["refresh"].done = {s: date(2026, 10, 29) for s in SYMBOLS}
    step.benchmarks_step(_ctx(AFTER_CLOSE))
    assert [h[0] for h in env["history"]] == list(SYMBOLS)
    for _, start, sessions, through in env["history"]:
        assert start < SINCE and sessions == ALL_SESSIONS and through == date(2026, 11, 4)
    assert env["bars"].upserts == 4 and len(env["bars"].rows) == 4 * len(ALL_SESSIONS)
    assert all(r["final"] for r in env["bars"].rows.values())
    assert env["refresh"].done == {s: date(2026, 11, 4) for s in SYMBOLS}
    assert set(env["asker"]) == {Asker.ADMIN_REFRESH}


def test_the_next_cycle_never_refetches_a_refreshed_day(env):
    step.benchmarks_step(_ctx(AFTER_CLOSE))
    env["history"].clear()
    step.reset_state()   # even a restarted process reads the stored guard
    step.benchmarks_step(_ctx(AFTER_CLOSE + timedelta(seconds=30)))
    assert env["history"] == []


def test_a_refresh_without_the_last_close_is_retried_later_not_marked(env):
    env["through"] = date(2026, 11, 3)
    step.benchmarks_step(_ctx(AFTER_CLOSE))
    assert env["refresh"].done == {}
    env["history"].clear()
    step.benchmarks_step(_ctx(AFTER_CLOSE + timedelta(seconds=60)))
    assert env["history"] == []
    env["through"] = None
    step.benchmarks_step(_ctx(AFTER_CLOSE + timedelta(seconds=step.FULL_RETRY_S)))
    assert len(env["history"]) == 4
    assert env["refresh"].done == {s: date(2026, 11, 4) for s in SYMBOLS}


@pytest.mark.parametrize("now, last", [
    (datetime(2026, 11, 27, 18, 30, tzinfo=UTC), date(2026, 11, 27)),   # 13:30 ET, half day closed
    (datetime(2026, 11, 27, 17, 30, tzinfo=UTC), date(2026, 11, 25)),   # 12:30 ET, still open
])
def test_a_half_day_close_gates_the_final_bar(now, last):
    assert step.last_completed_session(now) == last


def test_in_session_today_is_upserted_not_final_at_most_every_five_minutes(env):
    env["refresh"].done = {s: date(2026, 11, 3) for s in SYMBOLS}
    env["bars"].rows = {(s, date(2026, 11, 3)): _bar(s, date(2026, 11, 3)) for s in SYMBOLS}
    step.benchmarks_step(_ctx(IN_SESSION, "regular"))
    today = {s: env["bars"].rows[(s, date(2026, 11, 4))] for s in SYMBOLS}
    assert all(r["final"] is False and r["as_of"] == IN_SESSION for r in today.values())
    assert today["SPY"]["day_pct"] == pytest.approx(0.01)
    assert env["history"] == []          # yesterday already refreshed
    step.benchmarks_step(_ctx(IN_SESSION + timedelta(seconds=60), "regular"))
    assert len(env["prices"]) == 1
    step.benchmarks_step(_ctx(IN_SESSION + timedelta(seconds=step.INTRADAY_EVERY_S), "regular"))
    assert len(env["prices"]) == 2


@pytest.mark.parametrize("state", ["extended", "closed"])
def test_no_intraday_row_outside_the_regular_session(env, state):
    env["refresh"].done = {s: date(2026, 11, 4) for s in SYMBOLS}
    step.benchmarks_step(_ctx(AFTER_CLOSE, state))
    assert env["prices"] == []


def test_a_failure_is_swallowed_and_leaves_the_cycle_error_alone(env, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError('relation "benchmark_bars" does not exist')
    monkeypatch.setattr(step, "live_since", boom)
    before = sw.snapshot().get("ops.refresher.benchmarks", {}).get("count", 0)
    ctx = _ctx(AFTER_CLOSE)
    step.benchmarks_step(ctx)
    assert ctx.report.error is None
    assert sw.snapshot()["ops.refresher.benchmarks"]["count"] == before + 1



def test_one_failed_history_fetch_leaves_other_symbols_and_intraday_running(env, monkeypatch):
    fetch_history = step.mb.history_with_fallback
    attempts = []

    def history(symbol, *args, **kwargs):
        attempts.append(symbol)
        if attempts == ["SPY"]:
            raise RuntimeError("SPY download failed")
        return fetch_history(symbol, *args, **kwargs)

    monkeypatch.setattr(step.mb, "history_with_fallback", history)
    before = sw.snapshot().get("ops.refresher.benchmarks", {}).get("count", 0)
    ctx = _ctx(IN_SESSION, "regular")
    step.benchmarks_step(ctx)

    previous = date(2026, 11, 3)
    today = date(2026, 11, 4)
    assert ctx.report.error is None
    assert sw.snapshot()["ops.refresher.benchmarks"]["count"] == before + 1
    assert attempts == list(SYMBOLS)
    assert env["refresh"].done == {s: previous for s in SYMBOLS if s != "SPY"}
    assert env["bars"].rows[("QQQ", today)]["final"] is False

    step.benchmarks_step(_ctx(IN_SESSION + timedelta(seconds=60), "regular"))
    assert attempts == list(SYMBOLS)
    step.benchmarks_step(_ctx(IN_SESSION + timedelta(seconds=step.FULL_RETRY_S), "regular"))
    assert attempts == [*SYMBOLS, "SPY"]
    assert env["refresh"].done["SPY"] == previous
    assert env["bars"].rows[("SPY", today)]["final"] is False


class FakeEquity:
    def __init__(self, live, backfill):
        self.edges = {"live": live, "backfill": backfill}

    def earliest_at(self, source, conn=None):
        return self.edges[source]


@pytest.mark.parametrize("live, backfill, expected", [
    (datetime(2026, 10, 1, 14, 0, tzinfo=UTC), datetime(2026, 8, 8, 2, 0, tzinfo=UTC), date(2026, 8, 7)),
    (datetime(2026, 10, 1, 14, 0, tzinfo=UTC), None, date(2026, 10, 1)),
    (None, None, None),
])
def test_live_since_is_the_earliest_sample_of_any_source_as_an_ny_date(monkeypatch, live, backfill, expected):
    monkeypatch.setattr(step, "equity_samples_repo", lambda: FakeEquity(live, backfill))
    assert step.live_since() == expected
