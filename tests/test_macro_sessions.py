import datetime as dt

from swingbot.core.macro.sessions import (
    holidays, is_half_day, is_holiday, is_thin_window, session_flag,
)


def test_holiday_rules_2026():
    h = holidays(2026)
    assert "2026-01-01" in h                       # New Year's (Thursday)
    assert "2026-01-19" in h                       # MLK: 3rd Monday
    assert h["2026-04-03"] == "Good Friday"        # Easter 2026 = Apr 5
    assert "2026-06-19" in h                       # Juneteenth (Friday)
    assert "2026-07-03" in h                       # Jul 4 = Saturday -> observed Fri
    assert "2026-11-26" in h                       # Thanksgiving: 4th Thursday
    assert "2026-12-25" in h


def test_mourning_closures():
    assert is_holiday("2018-12-05")                # G.H.W. Bush
    assert is_holiday("2025-01-09")                # J. Carter


def test_half_days_2025():
    assert is_half_day("2025-07-03")               # Jul 4 2025 is a Friday
    assert is_half_day("2025-11-28")               # day after Thanksgiving
    assert is_half_day("2025-12-24")               # Christmas Eve (Wednesday)
    assert not is_half_day("2025-07-04")


def test_thin_windows():
    assert is_thin_window(dt.datetime(2026, 7, 14, 9, 45))[0]      # first 30 min
    assert not is_thin_window(dt.datetime(2026, 7, 14, 11, 0))[0]  # mid-session
    assert is_thin_window(dt.datetime(2026, 7, 14, 15, 55))[0]     # last 10 min
    thin, reason = is_thin_window(dt.datetime(2026, 12, 29, 11, 0))
    assert thin and "holiday week" in reason


def test_session_flag_shapes():
    assert session_flag("2026-06-19")["flag"] == "holiday"
    assert session_flag("2025-11-28")["flag"] == "half_day"
    assert session_flag("2026-07-14", dt.time(9, 45))["flag"] == "thin"
    assert session_flag("2026-07-14")["flag"] == "normal"


def test_new_years_on_saturday_is_not_observed():
    # NYSE does not observe New Year's when Jan 1 falls on a Saturday
    # (unlike every other holiday, which shifts to the Friday).
    assert dt.date(2022, 1, 1).weekday() == 5
    assert "2021-12-31" not in holidays(2021)
    assert "2022-01-01" not in holidays(2022)


def test_juneteenth_only_from_2022():
    assert "2021-06-18" not in holidays(2021) and "2021-06-19" not in holidays(2021)
    assert "2022-06-20" in holidays(2022)          # Jun 19 2022 = Sunday -> Monday
