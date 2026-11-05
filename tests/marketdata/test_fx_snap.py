"""v205 L1-a: the 08:00 Berlin snap, fx_snap.snap and fx_snap.pairs_in_use.

Fakes stand in for both repositories and the pair files. Every expected rate is
a literal read off the fixture frame by hand, never recomputed. FRAME, FakeDaily
and FakeCodes are imported by tests/refresher/test_fx_snap_step.py and
tests/scripts/test_backfill_fx_daily_rates.py (V205-14)."""
import ast
import os
import pathlib
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot.core.marketdata import fx, fx_snap

UTC = timezone.utc
FRAME = pd.DataFrame(
    {"Close": [0.9200, 0.8600, 0.8680, 0.8700, 0.8720]},
    index=pd.DatetimeIndex(["2026-03-27", "2026-10-23", "2026-11-02", "2026-11-03", "2026-11-04"]))


class FakeDaily:
    """fx_daily_rates with on-conflict-do-nothing semantics."""

    def __init__(self):
        self.rows: dict[tuple, dict] = {}
        self.inserts: list[list[dict]] = []

    def days_present(self, base, account, *, conn=None):
        return {day for (b, a, day) in self.rows if (b, a) == (base, account)}

    def insert_if_absent(self, rows, *, conn=None):
        rows = list(rows)
        self.inserts.append(rows)
        written = 0
        for row in rows:
            key = (row["base"], row["account"], row["day"])
            if key not in self.rows:
                self.rows[key] = dict(row)
                written += 1
        return written


class FakeCodes:
    def __init__(self, codes):
        self.codes = set(codes)

    def known_codes(self, *, conn=None):
        return set(self.codes)


@pytest.fixture
def world(monkeypatch):
    daily, codes = FakeDaily(), FakeCodes({"USD", "EUR"})
    frames, reads = {"USDEUR=X": FRAME}, []

    def pair_frame(pair, *, refresh=True):
        reads.append((pair, refresh))
        return frames.get(pair)
    monkeypatch.setattr(fx_snap, "fx_daily_rate_repo", lambda: daily)
    monkeypatch.setattr(fx_snap, "quote_currency_repo", lambda: codes)
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "_pair_frame", pair_frame)
    state = SimpleNamespace(daily=daily, codes=codes, frames=frames, reads=reads, written_at=None)
    monkeypatch.setattr(fx_snap, "_written_at", lambda base, account: state.written_at)
    monkeypatch.setattr(fx_snap, "_stale_logged", set())
    return state


def test_pairs_in_use_are_the_majors_of_known_codes_except_the_account(world, monkeypatch):
    world.codes.codes = {"USD", "GBp", "GBP", "ZAc", "EUR", "ILA"}
    assert fx_snap.pairs_in_use() == [("GBP", "EUR"), ("ILS", "EUR"), ("USD", "EUR"), ("ZAR", "EUR")]
    monkeypatch.setattr(fx, "account_currency_code", lambda: "GBP")
    world.codes.codes = {"GBp", "USD"}
    assert fx_snap.pairs_in_use() == [("USD", "GBP")]           # pence into pounds: no pair


def test_from_eight_berlin_the_day_gets_the_close_before_it(world):
    now = datetime(2026, 11, 4, 7, 0, tzinfo=UTC)                # 08:00 CET
    assert fx_snap.snap(now) == 1
    assert world.daily.rows == {("USD", "EUR", date(2026, 11, 4)): {
        "base": "USD", "account": "EUR", "day": date(2026, 11, 4), "rate": 0.8700,
        "bar_date": date(2026, 11, 3), "snapped_at": now, "source": "snap"}}
    assert world.reads == [("USDEUR=X", False)]                  # the file as it stands, no fetch


def test_two_cycles_on_one_berlin_day_write_once_and_keep_the_first_value(world):
    assert fx_snap.snap(datetime(2026, 11, 4, 7, 0, tzinfo=UTC)) == 1
    world.frames["USDEUR=X"] = FRAME.assign(Close=[0.9200, 0.8600, 0.8680, 0.9900, 0.8720])
    assert fx_snap.snap(datetime(2026, 11, 4, 15, 0, tzinfo=UTC)) == 0
    assert world.daily.rows[("USD", "EUR", date(2026, 11, 4))]["rate"] == 0.8700
    assert len(world.reads) == 1                                 # a present day reads no frame


@pytest.mark.parametrize("day,gate_utc_hour,rate,bar", [
    (date(2026, 3, 29), 6, 0.9200, date(2026, 3, 27)),          # CEST from 01:00 UTC: 08:00 = 06:00 UTC
    (date(2026, 10, 25), 7, 0.8600, date(2026, 10, 23)),        # CET again from 01:00 UTC: 08:00 = 07:00 UTC
])
def test_the_gate_is_eight_berlin_on_both_dst_switch_days(world, day, gate_utc_hour, rate, bar):
    just_before = datetime(day.year, day.month, day.day, gate_utc_hour - 1, 59, tzinfo=UTC)
    at_gate = datetime(day.year, day.month, day.day, gate_utc_hour, 0, tzinfo=UTC)
    assert fx_snap.snap(just_before) == 0 and world.daily.rows == {}
    assert fx_snap.snap(at_gate) == 1
    stored = world.daily.rows[("USD", "EUR", day)]
    assert (stored["rate"], stored["bar_date"]) == (rate, bar)


def test_after_midnight_berlin_before_eight_nothing_is_written(world):
    assert fx_snap.snap(datetime(2026, 11, 4, 23, 30, tzinfo=UTC)) == 0     # 00:30 Berlin 11-05
    assert world.daily.rows == {} and world.reads == []


def test_no_frame_or_a_stale_bar_writes_no_row(world):
    world.codes.codes = {"USD", "GBP"}                           # no GBPEUR=X file
    assert fx_snap.snap(datetime(2026, 11, 4, 9, 0, tzinfo=UTC)) == 1
    assert set(world.daily.rows) == {("USD", "EUR", date(2026, 11, 4))}
    world.daily.rows.clear()
    assert fx_snap.snap(datetime(2026, 11, 12, 9, 0, tzinfo=UTC)) == 0     # bar 11-04 is 8 days old


def test_a_frame_two_weekdays_behind_writes_nothing_until_it_catches_up(world):
    world.frames["USDEUR=X"] = FRAME.iloc[:4]                    # last bar Tue 11-03; D = Thu 11-05
    now = datetime(2026, 11, 5, 9, 0, tzinfo=UTC)
    assert fx_snap.snap(now) == 0 and world.daily.rows == {}
    world.frames["USDEUR=X"] = _with_bar(FRAME, "2026-11-05", 0.8730)   # fx_step: 11-04 final + 11-05 forming
    assert fx_snap.snap(now) == 1
    assert world.daily.rows[("USD", "EUR", date(2026, 11, 5))]["bar_date"] == date(2026, 11, 4)


def test_a_stale_frame_is_logged_once_per_pair_per_day(world, caplog):
    world.frames["USDEUR=X"] = FRAME.iloc[:4]
    now = datetime(2026, 12, 9, 9, 0, tzinfo=UTC)
    world.frames["USDEUR=X"] = FRAME.iloc[:3]
    with caplog.at_level("INFO", logger=fx_snap.log.name):
        fx_snap.snap(now)
        fx_snap.snap(now)
    assert len([r for r in caplog.records if "stale" in r.getMessage()]) == 1


def test_monday_needs_only_the_friday_bar(world):
    world.frames["USDEUR=X"] = pd.DataFrame(
        {"Close": [0.8650, 0.8640]}, index=pd.DatetimeIndex(["2026-10-29", "2026-10-30"]))
    world.written_at = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)        # refreshed Saturday
    assert fx_snap.snap(datetime(2026, 11, 2, 9, 0, tzinfo=UTC)) == 1      # Monday 11-02
    assert world.daily.rows[("USD", "EUR", date(2026, 11, 2))]["bar_date"] == date(2026, 10, 30)


# --- a bar still forming never backs a row (quant-engineer panel, BLOCKING) ---------------

def _with_bar(frame, day, close):
    return pd.concat([frame, pd.DataFrame({"Close": [close]}, index=pd.DatetimeIndex([day]))])


THU = datetime(2026, 11, 5, 7, 0, tzinfo=UTC)                     # 08:00 CET Thursday 11-05


def test_a_newest_bar_written_before_its_london_day_ended_writes_nothing(world, caplog):
    world.written_at = datetime(2026, 11, 4, 23, 30, tzinfo=UTC)   # 23:30 GMT Wed: 11-04 still forming
    with caplog.at_level("INFO", logger=fx_snap.log.name):
        assert fx_snap.snap(THU) == 0
        assert fx_snap.snap(THU) == 0
    assert world.daily.rows == {} and world.daily.inserts == [[], []]
    assert len([r for r in caplog.records if "forming" in r.getMessage()]) == 1


def test_a_later_bar_proves_the_bar_before_it_final_whatever_the_mtime(world):
    world.frames["USDEUR=X"] = _with_bar(FRAME, "2026-11-05", 0.8730)
    world.written_at = datetime(2026, 11, 4, 20, 0, tzinfo=UTC)    # the mtime alone proves nothing
    assert fx_snap.snap(THU) == 1
    stored = world.daily.rows[("USD", "EUR", date(2026, 11, 5))]
    assert (stored["rate"], stored["bar_date"]) == (0.8720, date(2026, 11, 4))


def test_a_weekday_mtime_past_midnight_without_that_days_bar_is_a_failed_fetch(world):
    world.written_at = datetime(2026, 11, 5, 0, 30, tzinfo=UTC)    # touched, but no 11-05 bar came
    assert fx_snap.snap(THU) == 0 and world.daily.rows == {}


@pytest.mark.parametrize("written_at,rows", [
    (datetime(2026, 10, 30, 21, 0, tzinfo=UTC), 0),                # Friday 21:00 GMT: still forming
    (datetime(2026, 10, 30, 23, 59, tzinfo=UTC), 0),
    (datetime(2026, 10, 31, 0, 0, tzinfo=UTC), 1),                 # London midnight (GMT) ends Friday
    (datetime(2026, 10, 31, 6, 0, tzinfo=UTC), 1),                 # Saturday: only weekend days since
])
@pytest.mark.parametrize("day", [date(2026, 10, 31), date(2026, 11, 1), date(2026, 11, 2)])
def test_weekend_and_monday_rows_need_a_file_written_after_friday_ended(world, written_at, rows, day):
    world.frames["USDEUR=X"] = FRAME.iloc[:2].pipe(_with_bar, "2026-10-30", 0.8640)
    world.written_at = written_at
    assert fx_snap.snap(datetime(day.year, day.month, day.day, 9, 0, tzinfo=UTC)) == rows
    if rows:
        stored = world.daily.rows[("USD", "EUR", day)]
        assert (stored["rate"], stored["bar_date"]) == (0.8640, date(2026, 10, 30))


@pytest.mark.parametrize("written_at,rows", [
    (datetime(2026, 10, 23, 22, 59, tzinfo=UTC), 0),               # 23:59 BST Friday
    (datetime(2026, 10, 23, 23, 0, tzinfo=UTC), 1),                # 00:00 BST Saturday
])
def test_the_london_midnight_follows_british_summer_time(world, written_at, rows):
    world.frames["USDEUR=X"] = FRAME.iloc[:2]                       # newest bar Friday 10-23
    world.written_at = written_at
    assert fx_snap.snap(datetime(2026, 10, 24, 9, 0, tzinfo=UTC)) == rows


def test_snap_equals_backfill_once_the_forming_bar_is_final(world):
    world.written_at = datetime(2026, 11, 4, 23, 30, tzinfo=UTC)   # 11-04 forming at 0.8720
    assert fx_snap.snap(THU) == 0
    assert fx_snap.backfill(start=date(2026, 11, 5), end=date(2026, 11, 5), now=THU) == 0
    final = _with_bar(FRAME.iloc[:4], "2026-11-04", 0.8755)        # the 11-05 fetch rewrote 11-04
    world.frames["USDEUR=X"] = _with_bar(final, "2026-11-05", 0.8760)
    world.written_at = datetime(2026, 11, 5, 8, 0, tzinfo=UTC)
    assert fx_snap.snap(THU) == 1
    snapped = world.daily.rows.pop(("USD", "EUR", date(2026, 11, 5)))
    assert fx_snap.backfill(start=date(2026, 11, 5), end=date(2026, 11, 5), now=THU) == 1
    backfilled = world.daily.rows[("USD", "EUR", date(2026, 11, 5))]
    assert (snapped["rate"], snapped["bar_date"]) == (backfilled["rate"], backfilled["bar_date"]) \
        == (0.8755, date(2026, 11, 4))


def test_backfill_never_writes_a_day_backed_by_a_forming_bar(world):
    world.written_at = datetime(2026, 11, 4, 23, 30, tzinfo=UTC)   # newest bar 11-04 forming
    fx_snap.backfill(start=date(2026, 11, 3), end=date(2026, 11, 7), now=THU)
    assert sorted(day for (_, _, day) in world.daily.rows) == [date(2026, 11, 3), date(2026, 11, 4)]


def test_written_at_is_the_pair_files_mtime_and_none_without_a_file(monkeypatch, tmp_path):
    path = tmp_path / "USDEUR=X.csv"
    monkeypatch.setattr(fx_snap.data_store, "cache_path", lambda ticker, interval: str(path))
    assert fx_snap._written_at("USD", "EUR") is None
    path.write_text("Date,Close\n")
    os.utime(path, (1_700_000_000, 1_700_000_000))
    assert fx_snap._written_at("USD", "EUR") == datetime.fromtimestamp(1_700_000_000, tz=UTC)


def test_a_naive_now_is_refused(world):
    with pytest.raises(ValueError, match="aware"):
        fx_snap.snap(datetime(2026, 11, 4, 9, 0))


def test_the_module_imports_nothing_from_admin_or_flask():
    tree = ast.parse(pathlib.Path(fx_snap.__file__).read_text(encoding="utf-8"))
    names = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(name.startswith(("swingbot.admin", "flask")) for name in names), names
