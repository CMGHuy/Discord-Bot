"""v205 L1-a: fx_snap.backfill, snap(D) == backfill(D), and the ops script.

Every expected rate is read off the fixture frame by hand, never recomputed."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.ops import backfill_fx_daily_rates as script
from swingbot.core.market.session import BERLIN_TZ
from swingbot.core.marketdata import fx, fx_snap
from tests.marketdata.test_fx_snap import FakeCodes, FakeDaily

UTC = timezone.utc
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)                  # 13:00 Berlin (CET)
WEEK = pd.DataFrame({"Close": [0.8650, 0.8640, 0.0, 0.8700]},   # Monday 11-02 closed at 0.0
                    index=pd.DatetimeIndex(["2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]))
EXPECTED = {                                                     # day -> (rate, bar_date), by hand
    date(2026, 10, 30): (0.8650, date(2026, 10, 29)),
    date(2026, 10, 31): (0.8640, date(2026, 10, 30)),
    date(2026, 11, 1): (0.8640, date(2026, 10, 30)),
    date(2026, 11, 2): (0.8640, date(2026, 10, 30)),
    date(2026, 11, 3): (0.8640, date(2026, 10, 30)),             # the 0.0 close is skipped
    date(2026, 11, 4): (0.8700, date(2026, 11, 3)),
}


@pytest.fixture
def world(monkeypatch):
    state = SimpleNamespace(daily=FakeDaily(), frames={"USDEUR=X": WEEK})
    monkeypatch.setattr(fx_snap, "fx_daily_rate_repo", lambda: state.daily)
    monkeypatch.setattr(fx_snap, "quote_currency_repo", lambda: FakeCodes({"USD", "EUR"}))
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "_pair_frame", lambda pair, *, refresh=True: state.frames.get(pair))
    return state


def _stored(daily):
    return {day: (row["rate"], row["bar_date"]) for (_, _, day), row in daily.rows.items()}


def test_backfill_fills_each_day_after_the_first_bar_through_berlin_today(world):
    assert fx_snap.backfill(now=NOW) == 6
    assert _stored(world.daily) == EXPECTED
    assert {(r["source"], r["snapped_at"]) for r in world.daily.rows.values()} == {("backfill", NOW)}


def test_a_gap_past_seven_days_leaves_those_days_without_a_row(world):
    world.frames["USDEUR=X"] = pd.DataFrame(
        {"Close": [0.90, 0.91]}, index=pd.DatetimeIndex(["2026-10-01", "2026-10-20"]))
    assert fx_snap.backfill(end=date(2026, 10, 21), now=NOW) == 8
    assert set(_stored(world.daily)) == {date(2026, 10, d) for d in range(2, 9)} | {date(2026, 10, 21)}


def test_start_and_end_bound_the_days(world):
    assert fx_snap.backfill(start=date(2026, 11, 2), end=date(2026, 11, 3), now=NOW) == 2
    assert set(_stored(world.daily)) == {date(2026, 11, 2), date(2026, 11, 3)}
    assert fx_snap.backfill(start=date(2026, 1, 1), end=date(2026, 10, 30), now=NOW) == 1   # never before bar 1 + 1


def test_a_rerun_writes_nothing_and_a_snapped_row_is_kept(world):
    snapped = {"base": "USD", "account": "EUR", "day": date(2026, 11, 4), "rate": 0.8711,
               "bar_date": date(2026, 11, 3), "snapped_at": NOW, "source": "snap"}
    world.daily.rows[("USD", "EUR", date(2026, 11, 4))] = dict(snapped)
    assert fx_snap.backfill(now=NOW) == 5
    assert world.daily.rows[("USD", "EUR", date(2026, 11, 4))] == snapped
    assert fx_snap.backfill(now=NOW) == 0


def test_snap_equals_backfill_on_every_day(world):
    fx_snap.backfill(now=NOW)
    backfilled = _stored(world.daily)
    for day in sorted(EXPECTED):
        world.daily = FakeDaily()
        assert fx_snap.snap(datetime(day.year, day.month, day.day, 8, 0, tzinfo=BERLIN_TZ)) == 1
        assert _stored(world.daily) == {day: backfilled[day]}, day


def test_a_long_history_is_inserted_in_chunks(world):
    days = pd.date_range("2019-01-01", periods=2600, freq="D")
    world.frames["USDEUR=X"] = pd.DataFrame({"Close": [0.9] * len(days)}, index=days)
    end = date(2019, 1, 1) + timedelta(days=2500)
    assert fx_snap.backfill(end=end, now=NOW) == 2500
    assert [len(batch) for batch in world.daily.inserts] == [1000, 1000, 500]


def test_the_dry_run_prints_counts_and_writes_nothing(world, capsys):
    assert script.main(["--dry-run", "--end", "2026-11-04"]) == 0
    out = capsys.readouterr().out
    assert "USDEUR planned=6" in out and "planned=6 (dry run: nothing written)" in out
    assert world.daily.inserts == []


def test_the_script_writes_and_prints_the_count(world, capsys):
    assert script.main(["--end", "2026-11-04"]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "written=6"
    assert script.main(["--end", "2026-11-04"]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "written=0"


@pytest.mark.parametrize("argv", [["--start", "2026-11-04", "--end", "2026-11-01"], ["--end", "11/04/2026"]])
def test_bad_arguments_exit_two(world, argv):
    with pytest.raises(SystemExit) as raised:
        script.main(argv)
    assert raised.value.code == 2
