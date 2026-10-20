"""v175: the book-status zone latch and its one-line scan hook.

No database: `book_status.scheduled_repo` is a dict-backed fake and
`book_status._closed_book` is monkeypatched. The band is a fixture dict
(`vb.variance_band` patched), except in the one test that runs the real
function on a tiny, insufficient book.
"""
import asyncio
import datetime as dt
import inspect
import threading
import types

import pytest

from swingbot.commands.scanning import book_status
from swingbot.commands.scanning import loops as loops_mod
from swingbot.core.analytics import variance_band as vb
from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.presentation.kinds import Kind


class _Repo:
    """scheduled_repo() stand-in: fired_on/mark over a dict, marks recorded."""

    def __init__(self, stored=None):
        self.rows = {} if stored is None else {book_status.ZONE_JOB: stored}
        self.marks = []

    def fired_on(self, job):
        return self.rows.get(job)

    def mark(self, job, value):
        self.rows[job] = value
        self.marks.append((job, value))


class _Chan:
    def __init__(self, *, fail=False):
        self.sent, self.fail = [], fail

    async def send(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("discord down")
        self.sent.append(kwargs)
        return types.SimpleNamespace(id=len(self.sent))     # a discord.Message stand-in


def _band(zone="rough"):
    return {
        "status": "ok", "scope": "whole_book", "asof": "2026-10-16", "days": 140, "weeks": 30,
        "pool": "v2",
        "composition": {"days_by_era": {"v2": 140, "legacy": 0}, "trades_by_horizon": {"4w": 180}},
        "horizons": [],
        "current": {"run": 5, "run_age_days": 8, "drawdown": 4.1, "drawdown_age_days": 15,
                    "run_zone": zone, "drawdown_zone": "normal", "zone": zone},
        "expr": {"value": 0.21, "n": 180, "start": "2026-03-02", "end": "2026-10-16",
                 "ci": [0.05, 0.37], "not_positive": False},
        "dollars": {"median_risk": 96.4, "drawdown_usd": 395.24},
    }


_INSUFFICIENT = {"status": "insufficient", "scope": "whole_book", "days": 40, "weeks": 9}


@pytest.fixture
def wire(monkeypatch):
    """Fake the store and the band; returns (repo, state). Set state["band"]
    between calls to move the book's zone."""
    def _wire(*, stored=None, band=None):
        repo = _Repo(stored)
        state = {"band": band if band is not None else _band(), "main_thread": None}

        def fake_band(closed):
            state["main_thread"] = threading.current_thread() is threading.main_thread()
            band_now = state["band"]
            if isinstance(band_now, Exception):
                raise band_now
            return band_now

        monkeypatch.setattr(book_status, "scheduled_repo", lambda: repo)
        monkeypatch.setattr(book_status, "_closed_book", lambda: [])
        monkeypatch.setattr(vb, "variance_band", fake_band)
        return repo, state
    return _wire


def _post(chan):
    return asyncio.run(book_status.post_book_status(chan))


@pytest.mark.parametrize("stored,zone,action", [
    ("normal", "rough", "post"), ("normal", "outside", "post"), ("rough", "outside", "post"),
    ("normal", "normal", "none"), ("rough", "rough", "none"), ("outside", "outside", "none"),
    ("outside", "rough", "reset"), ("outside", "normal", "reset"), ("rough", "normal", "reset"),
])
def test_next_action_ranks_zones(stored, zone, action):
    assert book_status.next_action(stored, zone) == action


@pytest.mark.parametrize("value,expected", [
    (None, "normal"), ("2026-10-01", "normal"), ("cleared", "normal"),
    ("normal", "normal"), ("rough", "rough"), ("outside", "outside"),
])
def test_stored_zone_reads_missing_or_unknown_as_normal(monkeypatch, value, expected):
    monkeypatch.setattr(book_status, "scheduled_repo", lambda: _Repo(value))
    assert book_status.stored_zone() == expected


def test_zone_job_key():
    assert book_status.ZONE_JOB == "variance_band:zone"


@pytest.mark.parametrize("stored,zone", [
    (None, "rough"), ("normal", "rough"), ("normal", "outside"), ("rough", "outside"),
])
def test_a_rise_posts_one_book_status_and_stores_the_zone(wire, stored, zone):
    repo, _ = wire(stored=stored, band=_band(zone))
    chan = _Chan()
    assert _post(chan) is True
    assert len(chan.sent) == 1
    embed = chan.sent[0]["embed"]
    assert embed.kind is Kind.BOOK_STATUS
    assert chan.sent[0]["content"] == "📉 BOOK · BOOK STATUS"
    assert repo.rows[book_status.ZONE_JOB] == zone
    assert repo.marks == [(book_status.ZONE_JOB, zone)]


@pytest.mark.parametrize("zone", ["normal", "rough", "outside"])
def test_the_same_zone_again_is_silent_and_writes_nothing(wire, zone):
    repo, _ = wire(stored=zone, band=_band(zone))
    chan = _Chan()
    assert _post(chan) is False
    assert chan.sent == [] and repo.marks == []


def test_a_fall_stores_the_lower_zone_and_posts_nothing_then_a_rise_posts_again(wire):
    repo, state = wire(stored="outside", band=_band("normal"))
    chan = _Chan()
    assert _post(chan) is False
    assert chan.sent == []
    assert repo.rows[book_status.ZONE_JOB] == "normal"

    state["band"] = _band("rough")
    assert _post(chan) is True
    assert len(chan.sent) == 1
    assert repo.rows[book_status.ZONE_JOB] == "rough"

    assert _post(chan) is False                  # still rough: silent
    assert len(chan.sent) == 1


def test_outside_falling_to_rough_is_silent(wire):
    repo, _ = wire(stored="outside", band=_band("rough"))
    chan = _Chan()
    assert _post(chan) is False
    assert chan.sent == []
    assert repo.marks == [(book_status.ZONE_JOB, "rough")]


def test_a_failed_send_stores_nothing_so_the_next_tick_retries(wire):
    repo, _ = wire(stored="normal", band=_band("rough"))
    assert _post(_Chan(fail=True)) is False
    assert repo.marks == []
    assert repo.rows[book_status.ZONE_JOB] == "normal"

    chan = _Chan()
    assert _post(chan) is True
    assert len(chan.sent) == 1
    assert repo.rows[book_status.ZONE_JOB] == "rough"


@pytest.mark.parametrize("stored", [None, "normal", "rough", "outside"])
def test_an_insufficient_band_posts_nothing_and_writes_nothing(wire, stored):
    repo, _ = wire(stored=stored, band=dict(_INSUFFICIENT))
    chan = _Chan()
    assert _post(chan) is False
    assert chan.sent == [] and repo.marks == []


def test_the_band_is_computed_off_the_event_loop(wire):
    _, state = wire(stored="normal", band=_band("normal"))
    _post(_Chan())
    assert state["main_thread"] is False


def test_an_exception_is_counted_and_never_raised(wire):
    swallowed_mod.reset()
    repo, _ = wire(stored="normal", band=RuntimeError("bootstrap exploded"))
    chan = _Chan()
    assert _post(chan) is False
    assert chan.sent == [] and repo.marks == []
    assert swallowed_mod.snapshot()["scan.book_status"]["count"] == 1
    swallowed_mod.reset()


def test_the_real_band_on_a_tiny_book_is_insufficient_and_silent(monkeypatch):
    repo = _Repo("outside")
    day = dt.date(2026, 1, 5)
    trades = [{"id": f"t{i}", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
               "exit_price": 95.0, "status": "loss", "plan_id": f"p{i}", "shares": 10.0,
               "closed_at": f"{(day + dt.timedelta(days=i)).isoformat()}T15:00:00+00:00"}
              for i in range(3)]
    monkeypatch.setattr(book_status, "scheduled_repo", lambda: repo)
    monkeypatch.setattr(book_status, "_closed_book", lambda: trades)
    chan = _Chan()
    assert _post(chan) is False
    assert chan.sent == [] and repo.marks == []


def test_closed_book_reads_every_ledger_and_keeps_closed_trades_only(monkeypatch):
    from swingbot.core.tracking import performance

    seen = {}
    rows = [{"id": "a", "status": "win", "ledger": "main"},
            {"id": "b", "status": "loss", "ledger": "weak"},
            {"id": "c", "status": "closed", "ledger": "main"},
            {"id": "d", "status": "open", "ledger": "main"}]

    class _FakeLog:
        def get_trades(self, **kwargs):
            seen.update(kwargs)
            return rows

    monkeypatch.setattr(performance, "TradeLog", _FakeLog)
    assert [t["id"] for t in book_status._closed_book()] == ["a", "b", "c"]
    assert seen == {"status": None, "limit": None, "ledger": None}


def test_the_scan_tick_calls_the_hook_right_after_the_provider_check():
    lines = [line.strip() for line in inspect.getsource(loops_mod._session_scan_tick).splitlines()]
    i = lines.index("await ops_watch.check_provider_health()")
    assert lines[i + 1] == "await book_status.post_book_status(channel)"
    assert sum("book_status" in line for line in lines) == 1
    assert loops_mod.book_status is book_status
