import json

import pytest

from swingbot.core.macro.calendar_events import events_between, events_on, load_events

FIXTURE = [
    {"date": "2026-07-14", "time_et": "08:30", "kind": "cpi", "label": "CPI release", "importance": 3},
    {"date": "2026-07-29", "time_et": "14:00", "kind": "fomc", "label": "FOMC decision", "importance": 3},
    {"date": "2026-07-02", "time_et": "08:30", "kind": "nfp", "label": "NFP release", "importance": 3},
    {"date": "2026-07-17", "time_et": "", "kind": "opex", "label": "OPEX", "importance": 1},
    {"date": "2026-07-20", "time_et": "08:30", "kind": "bogus", "label": "bad kind", "importance": 3},
    {"date": "2026-07-21", "time_et": "08:30", "kind": "cpi", "label": "bad importance", "importance": 9},
]


@pytest.fixture
def events_file(tmp_path):
    path = tmp_path / "event_history.json"
    path.write_text(json.dumps(FIXTURE), encoding="utf-8")
    return str(path)


def test_loader_validates_and_sorts(events_file):
    events = load_events(events_file)
    # invalid kind + invalid importance dropped; remainder date-sorted
    assert [e["kind"] for e in events] == ["nfp", "cpi", "opex", "fomc"]


def test_events_between_inclusive_bounds(events_file):
    events = load_events(events_file)
    window = events_between("2026-07-14", "2026-07-17", events)
    assert [e["kind"] for e in window] == ["cpi", "opex"]


def test_events_on(events_file):
    events = load_events(events_file)
    assert events_on("2026-07-29", events)[0]["kind"] == "fomc"
    assert events_on("2026-07-30", events) == []


def test_missing_file_degrades_to_empty(tmp_path):
    assert load_events(str(tmp_path / "nope.json")) == []


def test_shipped_fomc_history_is_sane():
    """The FOMC dates are hand-transcribed from the Fed's calendar pages, so
    guard the shape: 8 scheduled decision days per complete year (7-9 allows
    for the 2020 emergency cuts), all parseable ISO dates at 14:00 ET."""
    import datetime as dt

    from swingbot.core.macro.calendar_events import load_events as _load
    events = [e for e in _load() if e["kind"] == "fomc"]
    if not events:
        pytest.skip("event_history.json not generated yet")
    per_year: dict[str, int] = {}
    for e in events:
        dt.date.fromisoformat(e["date"])
        assert e["time_et"] == "14:00"
        per_year[e["date"][:4]] = per_year.get(e["date"][:4], 0) + 1
    current = dt.date.today().year
    for year, n in per_year.items():
        if int(year) < current:
            assert 7 <= n <= 9, f"{year}: {n} FOMC days"


import datetime as dt  # noqa: E402

import swingbot.core.macro.calendar_events as cal  # noqa: E402
import swingbot.core.macro.fred as fred  # noqa: E402


def test_refresh_merge_idempotent(tmp_path, monkeypatch):
    path = tmp_path / "event_history.json"
    path.write_text(json.dumps([FIXTURE[0]]), encoding="utf-8")   # cpi 2026-07-14 known
    monkeypatch.setattr(cal, "EVENTS_PATH", str(path))
    monkeypatch.setattr(cal, "FUTURE_FOMC", ["2026-07-29"])
    monkeypatch.setattr(fred, "fred_release_dates",
                        lambda rid, include_future=True: ["2026-07-14", "2026-08-12"])
    today = dt.date(2026, 7, 10)
    # 4 kinds x 2 dates = 8 pairs, minus (cpi, 07-14) already present,
    # plus the future FOMC = 8 rows added.
    assert cal.refresh_future_events(days_ahead=45, today=today) == 8
    assert cal.refresh_future_events(days_ahead=45, today=today) == 0   # idempotent
    assert len(cal.load_events()) == 9


def test_next_event_ordering_and_tz_math():
    events = sorted(FIXTURE[:3], key=lambda e: (e["date"], e["kind"]))
    now = dt.datetime(2026, 7, 14, 11, 0, tzinfo=dt.timezone.utc)   # 07:00 ET (EDT)
    nxt = cal.next_event(now=now, events=events)
    assert nxt["kind"] == "cpi"                       # today's 08:30 ET still ahead
    # 08:30 ET on 2026-07-14 = 12:30 UTC -> 1.5 h away
    assert cal.hours_until(nxt, now=now) == pytest.approx(1.5)
    later = dt.datetime(2026, 7, 14, 13, 0, tzinfo=dt.timezone.utc)
    assert cal.next_event(now=later, events=events)["kind"] == "fomc"
    assert cal.next_event(kinds=("nfp",), now=later, events=events) is None
