"""v209 A1: the outcome-blind validation-day selector (spec Amendment A1)."""
import json
import random
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "data"))
import shock_validation_days as sv  # noqa: E402

PRICE_COLS = ("spy_prev_close", "spy_open", "spy_close", "vix_prev_close", "vix_open", "vix_close")


def _table(rows):
    """rows: (date, spy_ret, qqq_ret, vix_chg); session_no is the row order."""
    df = pd.DataFrame({"session_no": range(len(rows)),
                       "spy_ret": [r[1] for r in rows], "qqq_ret": [r[2] for r in rows],
                       "vix_chg": [r[3] for r in rows]},
                      index=[r[0] for r in rows])
    for col in PRICE_COLS:
        df[col] = 100.0
    return df


def _bdays(start, n):
    return [d.date() for d in pd.bdate_range(start, periods=n)]


def _csv(path, rows, volume=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    head = "Date,Open,High,Low,Close" + (",Volume" if volume else "")
    lines = [head] + [f"{d},{o},{max(o, c)},{min(o, c)},{c}" + (",1" if volume else "")
                      for d, o, c in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_constants_are_the_pre_registered_values():
    assert sv.WINDOW == (date(2023, 1, 2), date(2025, 12, 31))
    assert (sv.SEED, sv.SPACING, sv.YEAR_CAP) == (209, 5, 4)
    assert sv.CLASS_ORDER == ("shock", "hard", "rotation", "calm")
    assert sv.CLASS_SIZES == {"shock": 6, "hard": 4, "rotation": 4, "calm": 12}


def test_load_daily_reads_both_csv_shapes(tmp_path):
    _csv(tmp_path / "s.csv", [("2023-01-04", 99.0, 101.0), ("2023-01-03", 100.0, 98.0)])
    _csv(tmp_path / "v.csv", [("2023-01-03", 20.0, 21.0)], volume=False)
    spy = sv.load_daily(tmp_path / "s.csv")
    assert list(spy.index) == [date(2023, 1, 3), date(2023, 1, 4)]
    assert spy.loc[date(2023, 1, 4), "Close"] == 101.0
    assert sv.load_daily(tmp_path / "v.csv").loc[date(2023, 1, 3), "Open"] == 20.0


def test_day_table_takes_prior_closes_from_before_the_window_and_needs_all_three(tmp_path):
    spy = [("2022-12-30", 100.0, 100.0), ("2023-01-03", 99.0, 98.0), ("2023-01-04", 98.0, 99.0)]
    qqq = [("2022-12-30", 200.0, 200.0), ("2023-01-03", 199.0, 194.0), ("2023-01-04", 194.0, 196.0)]
    vix = [("2022-12-30", 20.0, 20.0), ("2023-01-03", 21.0, 22.0)]           # 01-04 missing
    for name, rows in (("spy", spy), ("qqq", qqq), ("vix", vix)):
        _csv(tmp_path / f"{name}.csv", rows)
    table = sv.day_table(*(sv.load_daily(tmp_path / f"{n}.csv") for n in ("spy", "qqq", "vix")))
    assert list(table.index) == [date(2023, 1, 3)]
    row = table.loc[date(2023, 1, 3)]
    assert row["spy_ret"] == pytest.approx(-2.0) and row["qqq_ret"] == pytest.approx(-3.0)
    assert row["vix_chg"] == pytest.approx(10.0) and row["session_no"] == 1
    assert (row["spy_prev_close"], row["spy_open"], row["vix_open"]) == (100.0, 99.0, 21.0)


def test_shock_days_skip_anything_within_five_sessions():
    days = _bdays("2024-01-02", 40)
    rets = {0: -5.0, 5: -4.5, 6: -4.0, 12: -3.0, 20: -2.9, 25: -2.6, 30: -2.8, 39: -2.7}
    table = _table([(d, rets.get(i, 0.1), 0.1, 0.0) for i, d in enumerate(days)])
    assert sv.pick_shock(table, n=6, spacing=5) == [days[i] for i in (0, 6, 12, 20, 30, 39)]


def test_hard_negatives_are_the_largest_band_drops_with_calm_vix():
    days = _bdays("2024-03-01", 9)
    spy = [-2.6, -2.5, -2.0, -1.9, -1.8, -1.7, -1.6, -1.5, -1.4]
    vix = [5.0, 5.0, 20.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0]
    table = _table([(d, s, 0.0, v) for d, s, v in zip(days, spy, vix)])
    assert sv.pick_hard(table, set(), n=4) == [days[1], days[3], days[4], days[5]]
    assert sv.pick_hard(table, {days[1]}, n=4) == [days[3], days[4], days[5], days[6]]


def test_rotation_is_the_most_negative_qqq_shortfall_under_the_filters():
    days = _bdays("2024-05-01", 8)
    rows = [(days[0], 0.2, -1.5, 5.0),    # -1.7
            (days[1], -1.6, -4.0, 5.0),   # SPY below -1.5: out
            (days[2], -1.0, -2.5, 16.0),  # VIX +16 pct: out
            (days[3], 0.0, -1.0, 0.0),    # -1.0
            (days[4], -1.5, -2.0, 0.0),   # -0.5, SPY exactly -1.5 is in
            (days[5], 0.5, 0.1, 0.0),     # -0.4
            (days[6], 0.3, -0.9, 0.0),    # -1.2
            (days[7], 0.1, 0.5, 0.0)]     # +0.4
    table = _table(rows)
    assert sv.pick_rotation(table, set(), n=4) == [days[0], days[6], days[3], days[4]]
    assert sv.pick_rotation(table, {days[0]}, n=4) == [days[6], days[3], days[4], days[5]]


def test_calm_pool_filters_and_the_draw_is_seeded_with_a_year_cap():
    days = _bdays("2023-01-03", 780)
    rows = [(d, 0.1, 0.1, 0.0) for d in days]
    rows[1] = (days[1], 0.5, 0.1, 0.0)      # |SPY| not < 0.5
    rows[2] = (days[2], -0.2, 0.1, 3.0)     # VIX change not < +3
    table = _table(rows)
    pool = sv.calm_pool(table, {days[3]})
    assert days[1] not in pool and days[2] not in pool and days[3] not in pool
    assert pool == sorted(pool)
    order, expected, per_year = list(pool), [], {}
    random.Random(209).shuffle(order)
    for d in order:
        if per_year.get(d.year, 0) < 4:
            expected.append(d)
            per_year[d.year] = per_year.get(d.year, 0) + 1
        if len(expected) == 12:
            break
    picked = sv.pick_calm(table, {days[3]})
    assert picked == expected and len(picked) == 12
    assert max(sum(d.year == y for d in picked) for y in {d.year for d in picked}) <= 4


def _three_years():
    days = _bdays("2023-01-03", 760)
    rows = {i: (d, 0.1, 0.1, 0.0) for i, d in enumerate(days)}
    for i in (10, 20, 30, 40, 50):
        rows[i] = (days[i], -4.0, -4.0, 30.0)
    rows[60] = (days[60], -2.0, -2.0, 5.0)              # a band drop that is also a top-6 drop
    for i in (70, 80, 90, 100, 110):
        rows[i] = (days[i], -1.6, -1.6, 5.0)
    for i in range(120, 125):
        rows[i] = (days[i], 0.0, -2.0, 0.0)              # rotation and calm-eligible
    return days, _table([rows[i] for i in range(len(days))])


def test_classes_are_disjoint_and_taken_in_order():
    days, table = _three_years()
    out = sv.select_days(table)
    cls = out["classes"]
    assert days[60].isoformat() in cls["shock"] and days[60].isoformat() not in cls["hard"]
    assert cls["hard"] == [days[i].isoformat() for i in (70, 80, 90, 100)]
    assert cls["rotation"] == [days[i].isoformat() for i in (120, 121, 122, 123)]
    assert {k: len(v) for k, v in cls.items()} == sv.CLASS_SIZES
    every = [d for v in cls.values() for d in v]
    assert len(every) == len(set(every)) == 26
    assert set(out["days"]) == set(every)
    assert all(out["days"][d]["class"] == k for k, v in cls.items() for d in v)
    assert out["window"] == ["2023-01-02", "2025-12-31"] and out["seed"] == 209


def test_a_class_that_cannot_be_filled_raises():
    table = _table([(d, 0.1, 0.1, 0.0) for d in _bdays("2023-01-03", 700)])
    with pytest.raises(ValueError, match="shock"):
        sv.select_days(table)


def test_main_writes_the_list_once_and_refuses_to_overwrite(tmp_path, monkeypatch):
    rows = [("2022-12-30", 1.0, 1.0), ("2023-01-03", 1.0, 1.0)]
    _csv(tmp_path / "data/market_data_pit/daily/SPY.csv", rows)
    _csv(tmp_path / "data/market_data_pit/daily/QQQ.csv", rows)
    _csv(tmp_path / "market_data/vix/VIX_daily.csv", rows, volume=False)
    frozen = {"window": ["2023-01-02", "2025-12-31"], "seed": 209, "rules": "x",
              "classes": {}, "days": {}}
    monkeypatch.setattr(sv, "select_days", lambda table: frozen)
    out = tmp_path / "list.json"
    assert sv.main(["--data-root", str(tmp_path), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == frozen
    out.write_text("{}", encoding="utf-8")
    assert sv.main(["--data-root", str(tmp_path), "--out", str(out)]) == 2
    assert out.read_text(encoding="utf-8") == "{}"
