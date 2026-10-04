import datetime as dt
from zoneinfo import ZoneInfo

from swingbot.core.scanning import strategy_pass as sp
from tests.helpers import make_ohlcv

ET = ZoneInfo("America/New_York")


def _frame_ending(day):
    df = make_ohlcv([100 + i for i in range(80)], start=(day - dt.timedelta(days=60)).isoformat())
    return df[df.index.date <= day]


def test_completed_frame_and_deduplication():
    day = dt.date(2026, 9, 17)
    df = _frame_ending(day)
    assert sp.completed_frame(df, dt.datetime(2026, 9, 17, 11, tzinfo=ET)).index[-1].date() == dt.date(2026, 9, 16)
    assert sp.completed_frame(df, dt.datetime(2026, 9, 17, 16, 5, tzinfo=ET)).index[-1].date() == day

    class P:
        source, ticker, strategy, horizon_key, created_at = "strategy", "AAPL", "MACD", "3m", "2026-09-16"
    class Store:
        def all(self): return [P()]
    assert sp.already_emitted(Store(), "AAPL", "MACD", "3m", "2026-09-16")
    assert not sp.already_emitted(Store(), "AAPL", "MACD", "4m", "2026-09-16")


_NOW = dt.datetime(2026, 9, 16, 17, tzinfo=ET)


def _clear_snapshot():
    from swingbot.core.market.events import EarningsSnapshot
    return EarningsSnapshot(_NOW, (), True, "test")


def test_compression_signal_is_stamped_with_mode_and_bar_date_or_rejected():
    from types import SimpleNamespace
    from swingbot.core.market.strategy_types import COMPRESSION_SHORT
    frame = _frame_ending(dt.date(2026, 9, 16))
    added = []
    plan_store = SimpleNamespace(all=lambda: [], add=added.append)
    stamp = sp._compression_context("AAPL", COMPRESSION_SHORT, frame,
                                    sp._PassDeps(plan_store, None, "shadow", set(), None,
                                                 compression_of=lambda t, f: ("broad", None),
                                                 earnings_of=lambda t: _clear_snapshot(), now=_NOW))
    assert stamp == ({"compression_mode": "broad", "compression_bar_date": "2026-09-16"}, None)
    deps = sp._PassDeps(plan_store, None, "shadow", set(), None)
    assert sp._compression_context("AAPL", COMPRESSION_SHORT, frame, deps) == ({}, "no_context")
    assert sp._compression_context("AAPL", "MACD", frame, deps) == ({}, None)
    why = sp._PassDeps(plan_store, None, "shadow", set(), None,
                       compression_of=lambda t, f: (None, "unaligned_spy"))
    assert sp._compression_context("AAPL", COMPRESSION_SHORT, frame, why) == ({}, "unaligned_spy")


def test_compression_never_goes_live_unless_named_in_nonempty_allow_list():
    from swingbot.core.market.strategy_types import COMPRESSION_SHORT
    live = lambda allow: sp._PassDeps(None, None, "live", allow, None)
    assert not sp._goes_live(live(set()), COMPRESSION_SHORT)
    assert not sp._goes_live(live({"MACD"}), COMPRESSION_SHORT)
    assert sp._goes_live(live({COMPRESSION_SHORT}), COMPRESSION_SHORT)
    assert sp._goes_live(live(set()), "MACD")
    assert not sp._goes_live(sp._PassDeps(None, None, "shadow", {COMPRESSION_SHORT}, None), COMPRESSION_SHORT)


def test_compression_rejection_reasons_are_counted():
    from types import SimpleNamespace
    from swingbot.core.market.strategy_types import COMPRESSION_SHORT
    frame = _frame_ending(dt.date(2026, 9, 16))
    deps = sp._PassDeps(SimpleNamespace(all=lambda: []), None, "shadow", set(), lambda t: 50.0,
                        compression_of=lambda t, f: (None, "missing_sector"))
    result = sp.PassResult()
    sp._emit_signal(result, frame, ticker="AAPL", strategy=COMPRESSION_SHORT, direction="bullish",
                    horizon="2w", bar_date="2026-09-16", regime=None, deps=deps)
    assert result.compression_reasons == {"missing_sector": 1} and result.compression_rejected == 1
