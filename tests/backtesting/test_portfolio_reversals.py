"""portfolio_replay's one-per-ticker rule and reversal modelling.

The default path must be untouched -- every existing caller replays exactly
as before -- so the first test here pins that, and the rest exercise the two
new opt-in flags.
"""
import pytest

from swingbot.core.backtesting.backtest_wf import _early_exit_r, portfolio_replay


def _sig(date, ticker="AAPL", *, r=1.0, exit_date="2020-02-01",
         direction="bullish", entry=100.0, stop=95.0, strategy="RSI"):
    return {"date": date, "ticker": ticker, "sector": "Tech", "r_multiple": r,
            "exit_date": exit_date, "strategy": strategy, "outcome": "win",
            "direction": direction, "entry": entry, "stop_loss": stop}


def _replay(signals, **kw):
    return portfolio_replay(signals, throttles=False, heat_cap_pct=100.0,
                            sector_cap_pct=100.0, **kw)


# ── the early-exit R formula ────────────────────────────────────────────────

@pytest.mark.parametrize("direction,entry,stop,exit_px,expected", [
    ("bullish", 100.0, 95.0, 97.5, -0.5),    # long cut below entry
    ("bullish", 100.0, 95.0, 105.0, 1.0),    # long cut in profit
    ("bearish", 100.0, 105.0, 102.5, -0.5),  # short cut against
    ("bearish", 100.0, 105.0, 95.0, 1.0),    # short cut in profit
])
def test_early_exit_r_is_direction_adjusted(direction, entry, stop, exit_px, expected):
    pos = {"direction": direction, "entry": entry, "stop_loss": stop}
    assert _early_exit_r(pos, exit_px) == pytest.approx(expected)


def test_early_exit_r_zero_risk_does_not_divide_by_zero():
    assert _early_exit_r({"direction": "bullish", "entry": 100.0, "stop_loss": 100.0}, 90.0) == 0.0


# ── defaults unchanged ──────────────────────────────────────────────────────

def test_default_blocks_concurrent_same_ticker_positions():
    """The default mirrors the live account's one-position-per-ticker rule."""
    out = _replay([_sig("2020-01-01"), _sig("2020-01-02")])
    assert out["trades_taken"] == 1
    assert out["trades_skipped"] == 1
    assert out["reversals"] == 0


# ── one position per ticker ─────────────────────────────────────────────────

def test_one_per_ticker_blocks_a_second_position():
    out = _replay([_sig("2020-01-01"), _sig("2020-01-02")], one_per_ticker=True)
    assert out["trades_taken"] == 1
    assert out["trades_skipped"] == 1


def test_one_per_ticker_allows_a_different_ticker():
    out = _replay([_sig("2020-01-01"), _sig("2020-01-02", ticker="MSFT")],
                  one_per_ticker=True)
    assert out["trades_taken"] == 2


def test_ticker_frees_up_after_its_exit_date():
    out = _replay([_sig("2020-01-01", exit_date="2020-01-10"),
                   _sig("2020-01-15", exit_date="2020-01-20")],
                  one_per_ticker=True)
    assert out["trades_taken"] == 2


def test_one_per_ticker_alone_never_reverses():
    """Opposite direction is still blocked, not flipped, unless reversals=True."""
    out = _replay([_sig("2020-01-01"),
                   _sig("2020-01-10", direction="bearish", entry=97.5, stop=102.0)],
                  one_per_ticker=True)
    assert out["trades_taken"] == 1 and out["reversals"] == 0


# ── reversals ───────────────────────────────────────────────────────────────

def test_opposite_signal_flips_the_position():
    out = _replay([_sig("2020-01-01", exit_date="2020-03-01"),
                   _sig("2020-01-10", direction="bearish", entry=97.5, stop=102.0)],
                  reversals=True, rev_min_hold_days=1)
    assert out["reversals"] == 1
    assert out["trades_taken"] == 2      # old cut short, new opened


def test_flip_banks_the_early_r_not_the_original():
    """Long entered at 100 (stop 95) cut at 97.5 books -0.5R, replacing the
    +1.0R it would have earned running to target. Delta must be -1.5R."""
    out = _replay([_sig("2020-01-01", r=1.0, exit_date="2020-03-01"),
                   _sig("2020-01-10", direction="bearish", entry=97.5, stop=102.0)],
                  reversals=True, rev_min_hold_days=1)
    assert out["reversals_r_delta"] == pytest.approx(-1.5)


def test_same_direction_never_flips():
    out = _replay([_sig("2020-01-01", exit_date="2020-03-01"),
                   _sig("2020-01-10", direction="bullish")],
                  reversals=True, rev_min_hold_days=1)
    assert out["reversals"] == 0
    assert out["trades_taken"] == 1      # blocked as a duplicate instead


def test_minimum_hold_blocks_an_immediate_flip():
    out = _replay([_sig("2020-01-01", exit_date="2020-03-01"),
                   _sig("2020-01-02", direction="bearish", entry=97.5, stop=102.0)],
                  reversals=True, rev_min_hold_days=10)
    assert out["reversals"] == 0


def test_cooldown_blocks_a_second_flip():
    sigs = [_sig("2020-01-01", exit_date="2020-06-01"),
            _sig("2020-01-20", direction="bearish", entry=97.0, stop=102.0,
                 exit_date="2020-06-01"),
            _sig("2020-01-22", direction="bullish", entry=98.0, stop=93.0,
                 exit_date="2020-06-01")]
    out = _replay(sigs, reversals=True, rev_min_hold_days=1, rev_cooldown_days=30)
    assert out["reversals"] == 1        # the 2020-01-22 flip is inside cooldown


def test_daily_cap_blocks_a_same_day_second_flip():
    sigs = [_sig("2020-01-01", exit_date="2020-06-01"),
            _sig("2020-01-20", direction="bearish", entry=97.0, stop=102.0,
                 exit_date="2020-06-01"),
            _sig("2020-01-20", direction="bullish", entry=98.0, stop=93.0,
                 exit_date="2020-06-01")]
    out = _replay(sigs, reversals=True, rev_min_hold_days=1,
                  rev_cooldown_days=0, rev_max_per_day=1)
    assert out["reversals"] == 1


def test_flip_without_direction_data_is_skipped_not_crashed():
    """Older signal dicts carry no direction/entry -- must degrade to the
    one-per-ticker block rather than raise."""
    bare = {"date": "2020-01-10", "ticker": "AAPL", "sector": "Tech",
            "r_multiple": 1.0, "exit_date": "2020-03-01", "strategy": "RSI",
            "outcome": "win"}
    out = _replay([_sig("2020-01-01", exit_date="2020-03-01"), bare], reversals=True)
    assert out["reversals"] == 0 and out["trades_taken"] == 1
