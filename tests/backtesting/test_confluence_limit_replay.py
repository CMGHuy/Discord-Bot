"""v212 replay module, part 1: scope, paired arms from one reference stream,
the outcome-blind census and frictions in net R. V212-11b's row tests import
the fixtures below."""
import pytest

from swingbot import config
from swingbot.core.backtesting import confluence_limit_replay as clr
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from tests.helpers import make_ohlcv

FLAT = [(100.0, 100.1, 99.9, 100.0)] * 20          # signal bar i = 19 (2021-01-29), M = 100
I = 19
TAIL = [(104.2, 106.5, 104.0, 106.3)] + [(106.3, 106.4, 106.2, 106.3)] * 6
DIP = (100.0, 100.2, 98.0, 99.0)                  # trades through 98.5, only touches 98.0
TO_TP1 = (99.0, 104.5, 98.9, 104.2)
GAP_UNDER_STOP = (96.0, 96.5, 95.5, 96.2)         # opens under the 96.75 arm stop
FRICTION_CONFIG = (("SLIPPAGE_BPS", 5.0), ("COMMISSION_PER_TRADE", 1.0),
                   ("COMMISSION_RISK_BASIS", 100.0), ("CONFLUENCE_LIMIT_ENTRY_F", 0.0),
                   ("CONFLUENCE_STRUCTURAL_STOP_PCT", 0.0), ("CONFLUENCE_STOP_DROP_PCT", 0.0),
                   ("CONFLUENCE_ATR_STOP_FLOOR", 0.0))


@pytest.fixture(autouse=True)
def _frictions(monkeypatch):
    for attr, value in FRICTION_CONFIG:
        monkeypatch.setattr(config, attr, value, raising=False)


def ref_plan(direction="bullish", **kw):
    bull = direction == "bullish"
    base = dict(plan_id="r1", ticker="XYZ", created_at="2021-01-29", source="confluence",
                strategy="S/R Confluence", horizon_key="4w", direction=direction,
                entry_type="market", trigger_price=100.0, entry_price=100.0, expiry_bars=5,
                stop_loss=98.25 if bull else 101.75, tp1=104.0 if bull else 96.0,
                tp1_fraction=0.5, tp2=106.0 if bull else 94.0,
                breakeven_trigger_fraction=0.5, trail_atr_mult=2.5, quality_score=0,
                quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.ACTIVE, status_history=[],
                acceptance_level=97.0 if bull else 103.0)
    base.update(kw)
    return TradePlanV2(**base)


def frame(*bars):
    return make_ohlcv(FLAT + list(bars) + TAIL, start="2021-01-04")


def test_grid_and_cell_keys():
    assert clr.CELLS == ("f0.333", "f0.5", "f0.667")
    assert [clr.cell_key(f) for f in clr.F_GRID] == list(clr.CELLS)


@pytest.mark.parametrize("kw,expected", [
    ({}, True),
    ({"acceptance_level": 99.0}, False),          # within 2%: stop already on structure
    ({"acceptance_level": 98.0}, False),          # exactly 2%: out of scope
    ({"acceptance_level": None}, False),          # missing level: out, never a crash
    ({"entry_type": "stop_entry", "entry_price": None}, False),
    ({"source": "strategy"}, False),
])
def test_scope(kw, expected):
    assert clr.in_scope(ref_plan(**kw)) is expected


def test_arm_plans_keep_drop_and_never_touch_the_reference():
    ref = ref_plan()
    arms = clr.arm_plans(ref, min_rr=1.5)
    assert arms["f0.333"] == "limit_stop_beyond_cap"         # (99 - 96.75) / 99 > 2%
    assert (arms["f0.5"].trigger_price, arms["f0.5"].stop_loss) == (98.5, 96.75)
    assert arms["f0.667"].trigger_price == 98.0
    assert (ref.entry_type, ref.trigger_price, ref.stop_loss) == ("market", 100.0, 98.25)


def test_a_kept_arm_past_two_percent_raises(monkeypatch):
    bad = ref_plan(entry_type="limit", stop_loss=97.0, limit_entry_f=0.5)
    monkeypatch.setattr(clr, "apply_confluence_limit", lambda *a, **k: bad)
    with pytest.raises(ValueError, match="2%"):
        clr.arm_plans(ref_plan(), min_rr=1.5)


def test_paired_alerts_keep_in_scope_plans_only(monkeypatch):
    monkeypatch.setattr(clr, "replay_scenarios",
                        lambda *a, **k: [(I, ref_plan()), (I + 1, ref_plan(acceptance_level=None))])
    out = clr.paired_alerts("XYZ", frame(DIP, TO_TP1), "4w", gates={})
    assert [(i, sorted(arms)) for i, _, arms in out] == [(I, sorted(clr.CELLS))]


@pytest.mark.parametrize("gates,config_rr,dropped", [
    ({"min_risk_reward": 4.0}, 1.5, True),    # f0.5 R:R from L = 5.5 / 1.75 = 3.14
    ({"min_risk_reward": 1.5}, 4.0, False),
])
def test_paired_alerts_take_the_rr_floor_from_the_gates(monkeypatch, gates, config_rr, dropped):
    """The arms use the reference's R:R floor: a gates override wins over config."""
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", config_rr)
    monkeypatch.setattr(clr, "replay_scenarios", lambda *a, **k: [(I, ref_plan())])
    arm = clr.paired_alerts("XYZ", frame(DIP), "4w", gates=gates)[0][2]["f0.5"]
    assert (arm == "limit_rr_fail") is dropped


def test_arm_plans_refuse_a_reference_handed_back(monkeypatch):
    monkeypatch.setattr(clr, "apply_confluence_limit", lambda plan, *a, **k: plan)
    with pytest.raises(RuntimeError, match="disagree"):
        clr.arm_plans(ref_plan(), min_rr=1.5)


# Literal, not clr.GUARDED_KNOBS: dropping a knob from the module must fail a case.
V212_KNOBS = ("CONFLUENCE_LIMIT_ENTRY_F", "CONFLUENCE_STRUCTURAL_STOP_PCT",
              "CONFLUENCE_STOP_DROP_PCT", "CONFLUENCE_ATR_STOP_FLOOR")


@pytest.mark.parametrize("knob", V212_KNOBS)
def test_the_guard_refuses_a_live_knob(monkeypatch, knob):
    monkeypatch.setattr(config, knob, 0.5)
    with pytest.raises(RuntimeError, match="must be 0"):
        clr.paired_alerts("XYZ", frame(DIP), "4w", gates={})


def test_census_is_outcome_blind_and_counts_fills():
    df, ref = frame(DIP, TO_TP1), ref_plan()
    row = clr.census_row(df, I, ref, clr.arm_plans(ref, min_rr=1.5))
    assert row["key"] == "XYZ|4w|2021-01-29|bullish"
    assert row["drops"] == {"f0.333": "limit_stop_beyond_cap", "f0.5": None, "f0.667": None}
    assert row["fill_state"] == {"f0.333": None, "f0.5": "filled", "f0.667": "tp1_cancel"}
    assert row["filled"] == {"f0.333": False, "f0.5": True, "f0.667": False}
    assert row["d_pct"] == pytest.approx(3.0)
    assert "r_net" not in row and "outcome" not in row


def test_census_counts_a_gap_stop_as_a_fill():
    df, ref = frame(GAP_UNDER_STOP), ref_plan()
    row = clr.census_row(df, I, ref, clr.arm_plans(ref, min_rr=1.5))
    assert row["fill_state"]["f0.5"] == "gap_stopped" and row["filled"]["f0.5"] is True


def test_census_expires_after_three_bars():
    quiet = (100.0, 100.1, 99.9, 100.0)
    df, ref = make_ohlcv(FLAT + [quiet] * 4 + [DIP] + TAIL, start="2021-01-04"), ref_plan()
    assert clr.census_row(df, I, ref, clr.arm_plans(ref, min_rr=1.5))["fill_state"]["f0.5"] == "expired"


@pytest.mark.parametrize("quiet_bars,state", [(2, "filled"), (3, "expired")])
def test_census_life_ends_on_the_third_bar(quiet_bars, state):
    """The dip on t+3 fills, on t+4 it is past the three-bar life."""
    quiet = (100.0, 100.1, 99.9, 100.0)
    df, ref = make_ohlcv(FLAT + [quiet] * quiet_bars + [DIP] + TAIL, start="2021-01-04"), ref_plan()
    assert clr.census_row(df, I, ref, clr.arm_plans(ref, min_rr=1.5))["fill_state"]["f0.5"] == state


def test_census_never_fills_on_the_signal_bar():
    """The limit rests from t+1: a dip on bar t itself is not a fill."""
    quiet = (100.0, 100.1, 99.9, 100.0)
    df, ref = make_ohlcv(FLAT[:-1] + [DIP] + [quiet] * 4 + TAIL, start="2021-01-04"), ref_plan()
    assert clr.census_row(df, I, ref, clr.arm_plans(ref, min_rr=1.5))["fill_state"]["f0.5"] == "expired"


@pytest.mark.parametrize("after", [0, 1, 2])
def test_census_expires_at_the_frame_end(after):
    """A signal 0-2 bars before the last bar: the life is capped, never an IndexError."""
    quiet = (100.0, 100.1, 99.9, 100.0)
    df, ref = make_ohlcv(FLAT + [quiet] * after, start="2021-01-04"), ref_plan()
    assert clr.census_row(df, I, ref, clr.arm_plans(ref, min_rr=1.5))["fill_state"]["f0.5"] == "expired"


def test_census_mirrors_for_a_short():
    ref = ref_plan("bearish")
    df = frame((100.0, 101.6, 99.9, 101.0), (101.0, 101.1, 95.5, 95.8))
    row = clr.census_row(df, I, ref, clr.arm_plans(ref, min_rr=1.5))
    assert row["filled"] == {"f0.333": False, "f0.5": True, "f0.667": False}


def test_net_r_long_and_short():
    # long: entry 100.05, exit 101.949 -> 0.9495 - 0.02 commission
    assert clr.net_r("bullish", 100.0, [(1.0, 102.0)], 2.0, 3) == pytest.approx(0.9295)
    # short: entry 99.95, exit 98.049 -> 0.9505 - 0.02 - 0.25 borrow (365 days)
    assert clr.net_r("bearish", 100.0, [(1.0, 98.0)], 2.0, 365) == pytest.approx(0.6805)
    # a gap stop: entry = exit = the open, risk 1.75 -> frictions only:
    # entry 96.048, exit 95.952 -> -0.096 / 1.75 = -0.054857 - 0.02 = -0.074857
    assert clr.net_r("bullish", 96.0, [(1.0, 96.0)], 1.75, 0) == pytest.approx(-0.0749, abs=1e-4)
    # two legs: entry 100.05; 0.5 x (103.948 - 100.05) = 1.949,
    # 0.5 x (105.947 - 100.05) = 2.9485; 4.8975 / 2 = 2.44875 - 0.02 = 2.42875
    assert clr.net_r("bullish", 100.0, [(0.5, 104.0), (0.5, 106.0)], 2.0, 3) == pytest.approx(2.42875)
    with pytest.raises(ValueError):
        clr.net_r("bullish", 100.0, [(1.0, 102.0)], 0.0, 3)


def test_census_window_filters_on_the_signal_date(monkeypatch):
    monkeypatch.setattr(clr, "replay_scenarios", lambda *a, **k: [(I, ref_plan())])
    df = frame(DIP, TO_TP1)
    assert clr.census("XYZ", df, ["4w"], ("2021-02-01", None)) == []
    assert len(clr.census("XYZ", df, ["4w"], ("2021-01-29", "2021-01-29"))) == 1
    one = clr.census("XYZ", df, ["4w"], (None, None), cells=(0.5,))
    assert list(one[0]["drops"]) == ["f0.5"]
