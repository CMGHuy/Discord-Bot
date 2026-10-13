"""v139 arm S replay on frozen fixtures: the baseline and every ceiling come
from the same scenarios; only clamped plans within c - 0.25 change, and they
keep their level; the census reads no outcome."""
import pytest

from swingbot import config
from swingbot.core.backtesting import confluence_stop_replay as csr
from tests.backtesting.test_backtest_scenarios import GATES, _structured_df
from tests.fixtures.ohlcv_parity import load_ohlcv

pytestmark = pytest.mark.slow

KEYS = ("c3", "c4", "c5")


@pytest.fixture(scope="module")
def frame():
    return load_ohlcv("DELL").loc[:"2019-12-31"]


@pytest.fixture(scope="module")
def pairs(frame):
    return csr.paired_plans("DELL", frame, "4w", gates=GATES)


def test_grid_and_keys_are_frozen():
    assert csr.C_STEPS == (3.0, 4.0, 5.0)
    assert tuple(csr.cell_key(c) for c in csr.C_STEPS) == KEYS


def test_knobs_must_be_off_while_measuring(frame, monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_STRUCTURAL_STOP_PCT", 3.0)
    with pytest.raises(RuntimeError, match="must be 0 while measuring"):
        csr.paired_plans("DELL", frame, "4w", gates=GATES)


def test_paired_plans_share_every_entry(pairs):
    assert len(pairs) == 40
    for _, base, cells in pairs:
        assert set(cells) == set(KEYS)
        for plan in cells.values():
            assert (plan.direction, plan.trigger_price, plan.acceptance_level) == \
                (base.direction, base.trigger_price, base.acceptance_level)


def test_only_clamped_plans_within_c_change_and_they_keep_their_level(pairs):
    moved = 0
    for _, base, cells in pairs:
        d = csr.plan_distance(base)
        assert base.stop_ceiling_pct is None
        for c in csr.C_STEPS:
            plan = cells[csr.cell_key(c)]
            if plan.stop_ceiling_pct is None:
                assert (plan.stop_loss, plan.tp1, plan.tp2) == (base.stop_loss, base.tp1, base.tp2)
                continue
            moved += 1
            assert d is not None and d <= c - 0.25 + 1e-9
            assert plan.stop_ceiling_pct == c
            assert plan.stop_loss == base.acceptance_level
    assert moved > 0, "arm S must move at least one DELL plan"


def test_census_rows_match_the_measured_fixture(frame, pairs):
    rows = [csr.census_row(frame, i, base, cells, csr.C_STEPS) for i, base, cells in pairs]
    clamped = [r for r in rows if r["clamped"]]
    assert len(rows) == 40 and len(clamped) == 9
    for c, applies in zip(csr.C_STEPS, (2, 6, 8)):     # d <= 2.75 / 3.75 / 4.75
        key = csr.cell_key(c)
        assert sum(r["changed"][key] or r["rollback"][key] for r in rows) == applies
        assert not any(r["changed"][key] and r["rollback"][key] for r in rows)
    assert not any(key in rows[0] for key in ("baseline", "cells", "outcome"))


def test_census_simulates_no_exit_and_respects_the_window(frame, pairs, monkeypatch):
    monkeypatch.setattr(csr, "paired_plans", lambda *a, **k: pairs)
    monkeypatch.setattr(csr, "simulate_exit", lambda *a, **k: pytest.fail("census read an outcome"))
    dates = sorted(str(frame.index[i].date()) for i, _, _ in pairs)
    start = dates[len(dates) // 2]
    rows = csr.census("DELL", frame, ("4w",), start=start)
    assert len(rows) == sum(date >= start for date in dates)


def test_entry_rows_reuse_the_baseline_for_unchanged_cells(frame, pairs, monkeypatch):
    monkeypatch.setattr(csr, "paired_plans", lambda *a, **k: pairs)
    rows = csr.replay_entries("DELL", frame, ("4w",))
    assert rows and all(r["arm"] == "S" for r in rows)
    for r in rows:
        for key in KEYS:
            if not r["changed"][key]:
                assert r["cells"][key] == r["baseline"]
    record = next(r["baseline"] for r in rows if r["baseline"] is not None)
    assert {"exit_mix", "gap_through", "fill_beyond_ceiling", "planned_rr"} <= set(record)


def test_paired_plans_refuses_a_changed_entry_set(monkeypatch):
    real = csr._replay

    def dropping(ticker, df, horizon_key, c, gates):
        plans = real(ticker, df, horizon_key, c, gates)
        return plans[1:] if c == 4.0 else plans

    monkeypatch.setattr(csr, "_replay", dropping)
    with pytest.raises(RuntimeError, match="changed the entry set"):
        csr.paired_plans("AAPL", _structured_df(), "4w", gates=GATES)
