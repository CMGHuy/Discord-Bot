"""v205 L1-a: the 08:00 Berlin snap, fx_snap.snap and fx_snap.pairs_in_use.

Fakes stand in for both repositories and the pair files. Every expected rate is
a literal read off the fixture frame by hand, never recomputed. FRAME, FakeDaily
and FakeCodes are imported by tests/refresher/test_fx_snap_step.py and
tests/scripts/test_backfill_fx_daily_rates.py (V205-14)."""
import ast
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
    return SimpleNamespace(daily=daily, codes=codes, frames=frames, reads=reads)


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


def test_a_naive_now_is_refused(world):
    with pytest.raises(ValueError, match="aware"):
        fx_snap.snap(datetime(2026, 11, 4, 9, 0))


def test_the_module_imports_nothing_from_admin_or_flask():
    tree = ast.parse(pathlib.Path(fx_snap.__file__).read_text(encoding="utf-8"))
    names = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(name.startswith(("swingbot.admin", "flask")) for name in names), names
