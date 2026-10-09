"""v143 outcomes: the g125 / g100 copies move tp1 only and never touch the
original plan; an untriggered plan is not a trade."""
import dataclasses

from swingbot.core.backtesting import fvg_diagnostic as fd
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_single import _plan


def bull(**kw):
    return _plan(strategy=fd.STRATEGY, source="confluence", **kw)   # entry 100, stop 95, tp1 110


NO_FVG = fd.SignalContext(target=110.0, target_sources=("EMA 50",), stop=95.0,
                          stop_sources=("Swing Low",), tolerance_pct=5.0)


def test_geometry_copies_move_only_tp1_and_leave_the_original_alone():
    original = bull(tp2=120.0)
    before = dataclasses.asdict(original)
    g125, g100 = fd.geometry_plan(original, 1.25), fd.geometry_plan(original, 1.0)
    assert (g125.tp1, g100.tp1) == (106.25, 105.0)
    assert dataclasses.asdict(original) == before
    assert {**dataclasses.asdict(g100), "tp1": 110.0} == before
    assert fd.geometry_plan(original, None) is original
    short = bull(direction="bearish", stop_loss=104.0, tp1=90.0)
    assert fd.geometry_plan(short, 1.25).tp1 == 95.0


def test_entry_reference_prefers_the_entry_price():
    assert fd.entry_reference(bull(entry_price=101.0)) == 101.0
    assert fd.entry_reference(bull()) == 100.0


def test_a_nearer_target_turns_a_live_loss_into_a_win():
    df = make_ohlcv([100.0, (100.0, 105.5, 99.5, 101.0), (101.0, 101.5, 94.0, 94.5)])
    row = fd.trade_row(df, 0, bull(), NO_FVG)
    assert row["outcomes"]["g100"]["outcome"] == "win"
    assert row["outcomes"]["live"]["outcome"] != "win"
    assert row["outcomes"]["g100"]["exit_mix"].startswith("tp1+")
    assert row["signal_date"] == "2024-01-02" and row["year"] == "2024"
    assert row["features"]["fvg_role"] == "unidentified"


def test_an_untriggered_plan_is_not_a_trade():
    df = make_ohlcv([100.0, 99.0, 98.5, 98.0, 98.0])
    assert fd.trade_row(df, 0, bull(entry_type="stop_entry", trigger_price=103.0), NO_FVG) is None
