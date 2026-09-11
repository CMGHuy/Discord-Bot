import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from swingbot.core.market import earnings_calendar as ec
from swingbot.core.market.session import nyse_calendar

D, ET = dt.date.fromisoformat, ZoneInfo("America/New_York")


class Source:
    def __init__(self, *reports): self._reports = reports
    def reports(self, ticker): return list(self._reports)


@pytest.mark.parametrize(("hour", "expected"), [(6, ec.BEFORE_OPEN), (10, ec.UNCONFIRMED), (16, ec.AFTER_CLOSE)])
def test_classifies_eastern_timing(hour, expected):
    assert ec.classify_timing(dt.datetime(2026, 10, 29, hour, tzinfo=ET)) == expected


def test_reaction_distance_and_exposure():
    cal = nyse_calendar()
    assert ec.reaction_session(ec.Report(D("2026-09-11"), ec.AFTER_CLOSE), cal) == D("2026-09-14")
    assert ec.next_reaction_distance(11, [3, 10, 70]) == 59
    assert ec.is_exposed(1, 1) and not ec.is_exposed(0, 5)


def test_sessions_and_label_follow_reaction_rule():
    source = Source(ec.Report(D("2026-09-14"), ec.AFTER_CLOSE))
    assert ec.sessions_to_reaction("NVDA", D("2026-09-11"), source=source) == 2
    now = dt.datetime(2026, 9, 11, 10, tzinfo=ET)
    assert ec.earnings_label("NVDA", now, source=source) == ec.Label(D("2026-09-14"), ec.AFTER_CLOSE, 1)


def test_csv_source_validates_and_sorts(tmp_path):
    (tmp_path / "NVDA.csv").write_text("report_date,timing,report_ts_et\n2026-10-29,after_close,x\n2026-07-30,before_open,x\n")
    assert ec.CsvSource(tmp_path).reports("nvda") == [ec.Report(D("2026-07-30"), ec.BEFORE_OPEN), ec.Report(D("2026-10-29"), ec.AFTER_CLOSE)]
