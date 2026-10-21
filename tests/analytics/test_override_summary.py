"""v173 §3: summarise -- descriptive totals over the counted rows only."""
from datetime import date

import pytest

from swingbot.core.analytics import override_fidelity as of

SUMMARY_KEYS = {"n_by_status", "bulk_n", "bulk_dates", "approx_n", "counted_n",
                "sum_delta_r", "sum_delta_r_gross", "sum_delta_usd", "usd_missing_n",
                "helped", "hurt", "neutral", "splits"}


def row(delta=0.2, day=date(2026, 8, 3), *, status="resolved", bulk=False, approx=False,
        usd=None, gross=None, price_source=None, state="ACTIVE", horizon="2w",
        direction="bullish", plan_id="p"):
    """One OverrideRow. A resolved row's gross delta defaults to delta + 0.01."""
    resolved = status == "resolved"
    return of.OverrideRow(
        plan_id=plan_id, ticker="T", horizon=horizon, direction=direction,
        state_at_close=state, close_date=day, bulk=bulk, approx=approx,
        price_source=price_source or ("session_close" if approx else "quote"),
        status=status, actual_r=delta, engine_r=0.0 if resolved else None,
        delta_r=delta if resolved else None,
        delta_r_gross=(round(delta + 0.01, 3) if gross is None else gross) if resolved else None,
        actual_usd=None, engine_usd=None, delta_usd=usd if resolved else None,
        engine_exit_reason="timeout" if resolved else None,
        outcome=of.outcome_of(delta if resolved else None), source="manual")


def test_keys_and_the_empty_summary():
    out = of.summarise([])
    assert set(out) == SUMMARY_KEYS
    assert out["n_by_status"] == {s: 0 for s in of.STATUSES}
    assert len(out["n_by_status"]) == 8
    assert (out["bulk_n"], out["bulk_dates"], out["approx_n"], out["counted_n"]) == (0, {}, 0, 0)
    assert (out["sum_delta_r"], out["sum_delta_r_gross"], out["sum_delta_usd"],
            out["usd_missing_n"]) == (0.0, 0.0, 0.0, 0)
    assert (out["helped"], out["hurt"], out["neutral"]) == (0, 0, 0)
    assert out["splits"] == {"state_at_close": {}, "horizon": {}, "direction": {}}


def test_rows_partition_into_counted_status_bulk_and_approx():
    rows = [row(0.2, usd=20.0), row(-0.3, usd=-30.0), row(0.05, usd=5.0),
            row(status="stale"), row(status="unstamped", price_source="none"),
            row(0.9, date(2026, 9, 30), bulk=True), row(-0.9, date(2026, 9, 30), bulk=True),
            row(1.5, approx=True)]
    out = of.summarise(rows)
    assert out["n_by_status"]["resolved"] == 3
    assert (out["n_by_status"]["stale"], out["n_by_status"]["unstamped"]) == (1, 1)
    assert sum(out["n_by_status"].values()) == 5
    assert (out["bulk_n"], out["bulk_dates"], out["approx_n"], out["counted_n"]) == (
        2, {"2026-09-30": 2}, 1, 3)
    assert out["bulk_n"] + out["approx_n"] + sum(out["n_by_status"].values()) == len(rows)
    assert out["sum_delta_r"] == pytest.approx(-0.05, abs=1e-9)
    assert out["sum_delta_usd"] == pytest.approx(-5.0, abs=1e-9)
    assert (out["helped"], out["hurt"], out["neutral"]) == (1, 1, 1)   # 0.05 sits on the band


def test_the_before_costs_sum_covers_counted_rows_only():
    rows = [row(0.2, gross=0.25), row(-0.3, gross=-0.28), row(0.5, bulk=True, gross=0.6),
            row(0.4, approx=True, gross=0.45)]
    assert of.summarise(rows)["sum_delta_r_gross"] == pytest.approx(-0.03, abs=1e-9)


def test_bulk_dates_one_key_per_day_sorted():
    rows = [row(bulk=True, day=date(2026, 9, 30)), row(bulk=True, day=date(2026, 8, 1)),
            row(bulk=True, day=date(2026, 9, 30))]
    assert list(of.summarise(rows)["bulk_dates"].items()) == [("2026-08-01", 1), ("2026-09-30", 2)]


def test_rows_without_dollars_stay_in_the_r_sum_and_are_counted_missing():
    out = of.summarise([row(0.4, usd=40.0), row(0.6, usd=None)])
    assert out["sum_delta_r"] == pytest.approx(1.0)
    assert out["sum_delta_usd"] == pytest.approx(40.0)
    assert out["usd_missing_n"] == 1


@pytest.mark.parametrize("delta, outcome", [(0.051, "helped"), (0.05, "neutral"),
                                            (-0.05, "neutral"), (-0.051, "hurt")])
def test_the_dead_band_is_frozen_at_five_hundredths(delta, outcome):
    assert of.DEAD_BAND == 0.05
    out = of.summarise([row(delta)])
    assert out[outcome] == 1


def test_splits_cover_state_horizon_and_direction_over_counted_rows():
    rows = [row(0.5, usd=50.0, state="PARTIAL", horizon="4w", direction="bearish"),
            row(-0.2, usd=-20.0, state="ACTIVE", horizon="2w"),
            row(-0.1, usd=None, state="ACTIVE", horizon="2w"),
            row(9.9, state="ACTIVE", bulk=True)]
    splits = of.summarise(rows)["splits"]
    assert splits["state_at_close"] == {
        "ACTIVE": {"n": 2, "sum_delta_r": -0.3, "sum_delta_usd": -20.0},
        "PARTIAL": {"n": 1, "sum_delta_r": 0.5, "sum_delta_usd": 50.0}}
    assert set(splits["horizon"]) == {"2w", "4w"}
    assert splits["direction"]["bearish"]["n"] == 1
    assert splits["direction"]["bullish"]["n"] == 2
