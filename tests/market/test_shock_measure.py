"""v209 shock.py: types, rows and measure (spec § The reading, § Units)."""
import ast
import dataclasses
import json
import pathlib
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot.core.market import shock
from swingbot.core.market.shock import (LABELS, NameRow, ShockReading, ShockSnapshot,
                                        ShockThresholds, VixTape)

UTC = timezone.utc
T0 = datetime(2026, 11, 5, 15, 30, tzinfo=UTC)          # 10:30 ET
D0 = date(2026, 11, 5)
NO_VIX = VixTape(None, None, None)
TH = ShockThresholds(min_names=3)


def _full_reading(**over):
    base = dict(
        as_of=T0, session_date=D0, minutes_since_open=60.0, breadth_frac=0.45,
        sectors_down=4, sectors_total=6, breadth_speed=0.12, spy_atr_move=-1.8,
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
        atr_k=1.0, breadth_enter=0.40, sectors_frac=0.6, breadth_fast=0.25,
        speed_enter=0.10, vix_spike_pct=15.0, vix_relief=0.05, breadth_reenter=0.30,
        breadth_exit=0.20, recovery_vix_off_high_pct=5.0, recovery_spy_retrace=0.5,
        min_dwell_min=45, recovery_min_dwell_min=30, min_names=20, vix_max_age_s=600,
        open_settle_min=15, quote_max_age_s=300)


def test_reading_field_order_is_the_ledger_contract():
    assert [f.name for f in dataclasses.fields(ShockReading)] == [
        "as_of", "session_date", "minutes_since_open", "breadth_frac", "sectors_down",
        "sectors_total", "breadth_speed", "spy_atr_move", "qqq_atr_move", "spy_last",
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
