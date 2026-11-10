"""v209 shock.py: types, rows and measure (spec § The reading, § Units)."""
import ast
import dataclasses
import json
import pathlib
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot.core.market import shock
from swingbot.core.market.shock import (LABELS, NameRow, ShockReading, ShockSnapshot,
                                        ShockThresholds, VixTape, measure)

UTC = timezone.utc
T0 = datetime(2026, 11, 5, 15, 30, tzinfo=UTC)          # 10:30 ET
D0 = date(2026, 11, 5)
NO_VIX = VixTape(None, None, None)
TH = ShockThresholds(min_names=3)


def _full_reading(**over):
    base = dict(
        as_of=T0, session_date=D0, minutes_since_open=60.0, breadth_frac=0.45,
        sectors_down=4, sectors_total=6, depth_frac=0.6,
        breadth_speed=0.12, spy_atr_move=-1.8,
        qqq_atr_move=None, spy_last=490.0, spy_prev_close=500.0, spy_session_low=489.5,
        spy_new_low=True, spy_retrace=0.05, vix_level=21.13, vix_chg_pct=27.21,
        vix_session_high=21.5, vix_off_high_pct=1.77, n_names=42, insufficient=False)
    base.update(over)
    return ShockReading(**base)


def test_labels_are_the_three_states_in_order():
    assert LABELS == ("NORMAL", "SHOCK", "RECOVERY")
    assert (shock.NORMAL, shock.SHOCK, shock.RECOVERY) == LABELS


def test_threshold_defaults_equal_the_config_defaults():
    assert ShockThresholds() == ShockThresholds(
        atr_k=1.0, breadth_enter=0.40, depth_frac=0.50, breadth_majority=0.50,
        breadth_fast=0.25,
        speed_enter=0.10, vix_spike_pct=15.0, vix_relief=0.05, breadth_reenter=0.30,
        breadth_exit=0.20, recovery_vix_off_high_pct=5.0, recovery_spy_retrace=0.5,
        min_dwell_min=45, recovery_min_dwell_min=30, min_names=20, vix_max_age_s=600,
        open_settle_min=15, quote_max_age_s=300)


def test_reading_field_order_is_the_ledger_contract():
    assert [f.name for f in dataclasses.fields(ShockReading)] == [
        "as_of", "session_date", "minutes_since_open", "breadth_frac", "sectors_down",
        "sectors_total", "depth_frac",
        "breadth_speed", "spy_atr_move", "qqq_atr_move", "spy_last",
        "spy_prev_close", "spy_session_low", "spy_new_low", "spy_retrace", "vix_level",
        "vix_chg_pct", "vix_session_high", "vix_off_high_pct", "n_names", "insufficient"]


@pytest.mark.parametrize("value", [
    ShockThresholds(),
    NameRow("MU", "Information Technology", 98.0, 100.0, 2.0, True),
    VixTape(21.13, 27.21, T0),
    ShockSnapshot(T0, D0, 60.0, (), None, None, NO_VIX),
])
def test_every_type_is_frozen(value):
    first = dataclasses.fields(value)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(value, first, None)


def test_reading_round_trips_through_json_with_iso_times():
    reading = _full_reading()
    row = json.loads(json.dumps(reading.as_row()))
    assert row["as_of"] == "2026-11-05T15:30:00+00:00"
    assert row["session_date"] == "2026-11-05"
    assert row["qqq_atr_move"] is None and row["spy_new_low"] is True
    assert ShockReading.from_row(row) == reading


def test_round_trip_keeps_none_everywhere_a_field_allows_it():
    reading = _full_reading(breadth_frac=None, breadth_speed=None, spy_atr_move=None,
                            spy_last=None, spy_prev_close=None, spy_session_low=None,
                            spy_new_low=False, spy_retrace=None, vix_level=None,
                            vix_chg_pct=None, vix_session_high=None, vix_off_high_pct=None,
                            n_names=0, insufficient=True)
    assert ShockReading.from_row(json.loads(json.dumps(reading.as_row()))) == reading


def test_from_row_accepts_already_decoded_values():
    reading = _full_reading()
    assert ShockReading.from_row(dataclasses.asdict(reading)) == reading


def test_from_row_refuses_a_row_missing_a_field():
    row = _full_reading().as_row()
    del row["n_names"]
    with pytest.raises(TypeError):
        ShockReading.from_row(row)


def test_meets_tolerates_float_noise_and_never_meets_none():
    assert shock._meets(7 / 20, 0.40 - 0.05) is True
    assert shock._meets(0.3499, 0.35) is False
    assert shock._meets(None, 0.0) is False


def test_shock_module_imports_no_config_and_does_no_io():
    source = pathlib.Path(shock.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module)
    assert imported <= {"__future__", "math", "statistics", "dataclasses", "datetime",
                        "typing", "collections.abc"}


# --- measure (V209-2b) -----------------------------------------------------

def _row(ticker, move, sector="Tech", *, equity=True, atr=2.0, prev=100.0):
    """A name whose (last - prev_close) / atr14 is exactly `move`."""
    return NameRow(ticker, sector, prev + move * atr, prev, atr, equity)


def _snap(names, *, as_of=T0, session=D0, minutes=60.0, spy=None, qqq=None, vix=NO_VIX):
    return ShockSnapshot(as_of, session, minutes, tuple(names), spy, qqq, vix)


def _flat(n, sector="Flat"):
    return [_row(f"F{i}", 0.0, sector) for i in range(n)]


def _spy(last, prev=500.0, atr=5.0):
    return NameRow("SPY", None, last, prev, atr, False)


def _later(minutes):
    return T0 + timedelta(minutes=minutes)


def test_breadth_counts_equities_only_and_non_equities_never_contribute():
    names = [_row(f"D{i}", -1.5) for i in range(4)] + _flat(6)
    names += [_row(sym, -3.0, None, equity=False) for sym in ("XAUUSD", "XAGUSD", "GC=F")]
    reading = measure(_snap(names), None, TH)
    assert reading.n_names == 10
    assert reading.breadth_frac == pytest.approx(0.4)


def test_exactly_minus_one_atr_counts_as_down_and_just_above_does_not():
    reading = measure(_snap([_row("A", -1.0), _row("B", -0.99), _row("C", 0.5)]), None, TH)
    assert reading.breadth_frac == pytest.approx(1 / 3)


@pytest.mark.parametrize("bad", [
    NameRow("NOQ", "Tech", None, 100.0, 2.0, True),       # no fresh live quote
    NameRow("NOP", "Tech", 98.0, None, 2.0, True),        # no completed prior bar
    NameRow("NOA", "Tech", 98.0, 100.0, None, True),      # < 15 completed bars
    NameRow("ZER", "Tech", 98.0, 100.0, 0.0, True),       # degenerate ATR
    NameRow("NAN", "Tech", 98.0, 100.0, float("nan"), True),
])
def test_names_without_a_usable_ratio_are_excluded_from_n_names(bad):
    reading = measure(_snap(_flat(3) + [bad]), None, TH)
    assert reading.n_names == 3 and reading.breadth_frac == 0.0


def test_sectors_need_two_contributing_members_and_use_the_median():
    names = [
        _row("A1", -2.0, "Semis"), _row("A2", -1.5, "Semis"), _row("A3", 0.5, "Semis"),  # median -1.5
        _row("B1", -3.0, "Energy"),                                                     # 1 member
        _row("C1", 0.0, "Banks"), _row("C2", -0.2, "Banks"),                            # median -0.1
        _row("N1", -2.0, None),                                                          # no sector
    ]
    reading = measure(_snap(names), None, TH)
    assert (reading.sectors_down, reading.sectors_total) == (1, 2)
    assert reading.n_names == 7 and reading.breadth_frac == pytest.approx(4 / 7)
    assert reading.depth_frac == pytest.approx(3 / 5)


def test_depth_frac_weights_sectors_by_their_names():
    # one heavy sector down, two light ones flat: 1 of 3 sectors, but 6 of 10 names
    names = ([_row(f"T{i}", -1.5, "Tech") for i in range(6)]
             + [_row("B1", 0.0, "Banks"), _row("B2", 0.1, "Banks"),
                _row("E1", 0.0, "Energy"), _row("E2", -0.2, "Energy")])
    reading = measure(_snap(names), None, TH)
    assert (reading.sectors_down, reading.sectors_total) == (1, 3)
    assert reading.depth_frac == pytest.approx(0.6)


def test_depth_frac_is_none_without_a_two_member_sector():
    names = [_row("A", -2.0, "Semis"), _row("B", -2.0, "Energy"), _row("C", -2.0, None)]
    assert measure(_snap(names), None, TH).depth_frac is None


def test_a_row_without_depth_frac_is_refused():
    row = _full_reading().as_row()
    del row["depth_frac"]
    with pytest.raises(TypeError):
        ShockReading.from_row(row)


def test_empty_watchlist_is_insufficient_with_no_breadth():
    reading = measure(_snap([]), None, ShockThresholds())
    assert reading.n_names == 0 and reading.insufficient is True
    assert reading.breadth_frac is None and reading.breadth_speed is None
    assert (reading.sectors_down, reading.sectors_total) == (0, 0)
    assert reading.depth_frac is None


def test_insufficient_below_min_names_and_sufficient_at_it():
    th = ShockThresholds(min_names=5)
    assert measure(_snap(_flat(4)), None, th).insufficient is True
    assert measure(_snap(_flat(5)), None, th).insufficient is False


def test_measure_defaults_its_thresholds():
    reading = measure(_snap(_flat(20)), None)
    assert reading.insufficient is False and reading.n_names == 20


def test_breadth_speed_only_within_the_same_session():
    first = measure(_snap([_row("A", -2.0)] + _flat(3)), None, TH)                     # 0.25
    two_down = [_row("A", -2.0), _row("B", -2.0)] + _flat(2)                           # 0.50
    assert first.breadth_speed is None
    assert measure(_snap(two_down, as_of=_later(15)), first, TH).breadth_speed == pytest.approx(0.25)
    next_day = _snap(two_down, as_of=T0 + timedelta(days=1), session=D0 + timedelta(days=1))
    assert measure(next_day, first, TH).breadth_speed is None


def test_breadth_speed_ignores_an_insufficient_previous_reading():
    thin = measure(_snap(_flat(2)), None, TH)
    assert thin.insufficient is True
    later = _snap([_row("A", -2.0)] + _flat(3), as_of=_later(15))
    assert measure(later, thin, TH).breadth_speed is None


def test_spy_and_qqq_atr_moves_are_recorded():
    qqq = _row("QQQ", -1.25, None, equity=False)
    reading = measure(_snap(_flat(3), spy=_spy(490.0), qqq=qqq), None, TH)
    assert reading.spy_atr_move == pytest.approx(-2.0)
    assert reading.qqq_atr_move == pytest.approx(-1.25)
    assert (reading.spy_last, reading.spy_prev_close) == (490.0, 500.0)


def test_spy_session_low_runs_and_a_new_low_needs_an_earlier_same_session_reading():
    first = measure(_snap(_flat(3), spy=_spy(490.0)), None, TH)
    assert first.spy_session_low == 490.0 and first.spy_new_low is False
    bounce = measure(_snap(_flat(3), as_of=_later(15), spy=_spy(495.0)), first, TH)
    assert bounce.spy_session_low == 490.0 and bounce.spy_new_low is False
    assert bounce.spy_retrace == pytest.approx(0.5)
    lower = measure(_snap(_flat(3), as_of=_later(30), spy=_spy(489.0)), bounce, TH)
    assert lower.spy_session_low == 489.0 and lower.spy_new_low is True
    equal = measure(_snap(_flat(3), as_of=_later(45), spy=_spy(489.0)), lower, TH)
    assert equal.spy_new_low is False


def test_spy_retrace_is_one_when_the_session_never_traded_below_the_prior_close():
    assert measure(_snap(_flat(3), spy=_spy(503.0)), None, TH).spy_retrace == 1.0


def test_a_new_session_restarts_the_spy_low_and_prior_close():
    yesterday = measure(_snap(_flat(3), spy=_spy(480.0)), None, TH)
    today = measure(_snap(_flat(3), as_of=T0 + timedelta(days=1), session=D0 + timedelta(days=1),
                          spy=_spy(485.0, prev=482.0)), yesterday, TH)
    assert today.spy_session_low == 485.0 and today.spy_new_low is False
    assert today.spy_prev_close == 482.0 and today.spy_retrace == 1.0


def test_missing_spy_leaves_every_spy_field_empty():
    reading = measure(_snap(_flat(3)), None, TH)
    assert (reading.spy_atr_move, reading.spy_last, reading.spy_prev_close,
            reading.spy_session_low, reading.spy_retrace) == (None, None, None, None, None)
    assert reading.spy_new_low is False and reading.qqq_atr_move is None


def test_fresh_vix_fills_level_change_and_session_high():
    reading = measure(_snap(_flat(3), vix=VixTape(21.13, 27.21, T0 - timedelta(seconds=60))), None, TH)
    assert (reading.vix_level, reading.vix_chg_pct) == (21.13, 27.21)
    assert reading.vix_session_high == 21.13 and reading.vix_off_high_pct == 0.0


def test_vix_session_high_is_the_running_max_and_off_high_is_a_percent():
    first = measure(_snap(_flat(3), vix=VixTape(25.0, 30.0, T0)), None, TH)
    later = measure(_snap(_flat(3), as_of=_later(15), vix=VixTape(22.5, 15.0, _later(15))), first, TH)
    assert later.vix_session_high == 25.0
    assert later.vix_off_high_pct == pytest.approx(10.0)


@pytest.mark.parametrize("vix", [
    VixTape(None, None, None),                                   # no ^VIX row
    VixTape(20.0, 5.0, None),                                    # no timestamp
    VixTape(20.0, 5.0, T0 - timedelta(seconds=601)),             # older than SHOCK_VIX_MAX_AGE_S
])
def test_missing_or_stale_vix_is_none(vix):
    reading = measure(_snap(_flat(3), vix=vix), None, TH)
    assert (reading.vix_level, reading.vix_chg_pct, reading.vix_off_high_pct) == (None, None, None)
    assert reading.vix_session_high is None


def test_a_stale_vix_keeps_the_session_high_already_seen():
    first = measure(_snap(_flat(3), vix=VixTape(25.0, 30.0, T0)), None, TH)
    later = measure(_snap(_flat(3), as_of=_later(15), vix=VixTape(24.0, 20.0, T0)), first, TH)  # 900 s old
    assert later.vix_level is None and later.vix_session_high == 25.0
    assert later.vix_off_high_pct is None


def test_a_new_session_restarts_the_vix_high():
    first = measure(_snap(_flat(3), vix=VixTape(30.0, 30.0, T0)), None, TH)
    tomorrow = T0 + timedelta(days=1)
    today = measure(_snap(_flat(3), as_of=tomorrow, session=D0 + timedelta(days=1),
                          vix=VixTape(22.0, -10.0, tomorrow)), first, TH)
    assert today.vix_session_high == 22.0 and today.vix_off_high_pct == 0.0


def test_a_measured_reading_round_trips_through_json():
    names = [_row("A", -2.0, "Semis"), _row("B", -2.0, "Semis")] + _flat(2)
    reading = measure(_snap(names, spy=_spy(490.0), vix=VixTape(21.0, 20.0, T0)), None, TH)
    assert ShockReading.from_row(json.loads(json.dumps(reading.as_row()))) == reading
