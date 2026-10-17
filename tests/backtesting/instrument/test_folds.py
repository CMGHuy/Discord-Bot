"""v158 WC4: purged, embargoed anchored folds and out-of-fold pooling
(v136 spec section 1 "Folds"; "Testing": purge/embargo boundary trades)."""
import dataclasses
from datetime import date, timedelta

import pandas as pd
import pytest

from swingbot.core.backtesting.backtest import BacktestTrade
from swingbot.core.backtesting.instrument import folds
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.backtesting.instrument.folds import Fold, OutOfFold
from swingbot.core.market.strategy_types import HORIZONS, LEGACY_HORIZONS

V2 = resolve("v2")
FOLD_2014 = Fold(test_year=2014, train_start="2010-01-01", train_end="2013-12-31",
                 test_start="2014-01-01", test_end="2014-12-31")


def _t(entry, exit_, r=1.0):
    return BacktestTrade(entry_date=entry, exit_date=exit_, direction="long", entry=100.0,
                         stop_loss=95.0, take_profit=110.0,
                         outcome="win" if r > 0 else "loss", exit_price=100.0,
                         return_pct=0.0, r_multiple=r, holding_days=1)


def _days(trades):
    return [str(t.entry_date)[:10] for t in trades]


# --- anchored_folds -------------------------------------------------------------------

def test_v2_has_twelve_anchored_yearly_folds():
    got = folds.anchored_folds(V2)
    assert [f.test_year for f in got] == list(range(2014, 2026))
    assert got[0] == FOLD_2014
    assert got[-1] == Fold(test_year=2025, train_start="2010-01-01", train_end="2024-12-31",
                           test_start="2025-01-01", test_end="2025-12-31")


def test_every_v2_train_fold_is_anchored_and_ends_the_day_before_its_test_fold():
    for fold in folds.anchored_folds(V2):
        assert fold.train_start == V2.research_start
        day_before = date.fromisoformat(fold.test_start) - timedelta(days=1)
        assert fold.train_end == day_before.isoformat()
        assert fold.test_end <= V2.research_end


def test_v1_has_no_folds():
    assert folds.anchored_folds(resolve("v1")) == ()


def test_folds_refuse_fewer_than_four_training_years():
    spec = dataclasses.replace(V2, fold_test_years=(2013, 2014))
    with pytest.raises(ValueError, match="4 training years"):
        folds.anchored_folds(spec)


def test_folds_refuse_a_mid_year_research_start_short_of_four_full_training_years():
    """2010-07-01 .. 2013-12-31 is 3.5 years, not 4: calendar-year subtraction misses it."""
    spec = dataclasses.replace(V2, research_start="2010-07-01", fold_test_years=(2014, 2015))
    with pytest.raises(ValueError, match="4 training years"):
        folds.anchored_folds(spec)


def test_folds_refuse_a_test_year_inside_the_sealed_holdout():
    spec = dataclasses.replace(V2, fold_test_years=tuple(range(2014, 2027)))
    with pytest.raises(ValueError, match="holdout"):
        folds.anchored_folds(spec)


def test_folds_refuse_unsorted_or_duplicate_years():
    for years in ((2015, 2014), (2014, 2014)):
        with pytest.raises(ValueError, match="strictly increasing"):
            folds.anchored_folds(dataclasses.replace(V2, fold_test_years=years))


def test_folds_refuse_an_unknown_scheme_or_an_empty_year_list():
    with pytest.raises(ValueError, match="unknown fold scheme"):
        folds.anchored_folds(dataclasses.replace(V2, fold_scheme="rolling"))
    with pytest.raises(ValueError, match="fold_test_years"):
        folds.anchored_folds(dataclasses.replace(V2, fold_test_years=()))


# --- split_fold: membership by entry date ------------------------------------------------

def test_a_trade_belongs_to_the_test_fold_by_its_entry_date():
    trades = [_t("2013-12-31", "2013-12-31"), _t("2014-01-01", "2014-01-09"),
              _t("2014-12-31", "2015-02-01"), _t("2015-01-01", "2015-01-05")]
    train, test = folds.split_fold(trades, FOLD_2014, embargo_days=0)
    assert _days(test) == ["2014-01-01", "2014-12-31"]
    assert _days(train) == ["2013-12-31"]


def test_a_trade_before_the_train_start_is_in_neither_side():
    train, test = folds.split_fold([_t("2009-12-31", "2010-01-05")], FOLD_2014, embargo_days=0)
    assert (train, test) == ([], [])


# --- purge ------------------------------------------------------------------------------

def test_purge_drops_a_train_trade_exiting_on_or_after_the_test_start():
    kept = _t("2013-12-20", "2013-12-31")
    on_start = _t("2013-12-20", "2014-01-01")
    after = _t("2013-11-01", "2014-02-14")
    train, _ = folds.split_fold([kept, on_start, after], FOLD_2014, embargo_days=0)
    assert train == [kept]


def test_purge_treats_a_never_closed_train_trade_as_open_into_the_test_fold():
    train, _ = folds.split_fold([_t("2013-06-03", None)], FOLD_2014, embargo_days=0)
    assert train == []


def test_purge_off_keeps_trades_that_straddle_the_test_start():
    straddle = _t("2013-12-20", "2014-01-01")
    train, _ = folds.split_fold([straddle], FOLD_2014, embargo_days=0, purge=False)
    assert train == [straddle]


def test_test_side_trades_are_never_purged():
    """Purge thins train only: a test trade still open at the test end stays."""
    late = _t("2014-12-30", "2015-03-01")
    _, test = folds.split_fold([late], FOLD_2014, embargo_days=270)
    assert test == [late]


# --- embargo ----------------------------------------------------------------------------

def test_embargo_never_fires_under_anchored_folds():
    trades = [_t(f"{y}-0{m}-02", f"{y}-0{m}-20") for y in range(2010, 2016) for m in (2, 6)]
    for fold in folds.anchored_folds(V2)[:2]:
        assert (folds.split_fold(trades, fold, embargo_days=0)
                == folds.split_fold(trades, fold, embargo_days=270))


def test_embargo_drops_train_trades_entered_within_the_window_after_the_test_end():
    """A generic fold whose train side continues past the test fold."""
    fold = Fold(test_year=2014, train_start="2010-01-01", train_end="2016-12-31",
                test_start="2014-01-01", test_end="2014-12-31")
    before = _t("2013-06-03", "2013-07-01")
    inside_test = _t("2014-06-02", "2014-06-20")
    on_edge = _t("2015-01-30", "2015-02-10")   # test_end + 30 days: embargoed
    first_free = _t("2015-01-31", "2015-02-10")
    train, test = folds.split_fold([before, inside_test, on_edge, first_free], fold,
                                   embargo_days=30)
    assert train == [before, first_free]
    assert test == [inside_test]


def test_a_post_test_train_trade_is_left_to_the_embargo_not_the_purge():
    fold = Fold(test_year=2014, train_start="2010-01-01", train_end="2016-12-31",
                test_start="2014-01-01", test_end="2014-12-31")
    post = _t("2016-03-01", "2016-03-20")
    train, _ = folds.split_fold([post], fold, embargo_days=0)
    assert train == [post]


def test_split_fold_refuses_a_negative_embargo():
    with pytest.raises(ValueError, match="embargo_days"):
        folds.split_fold([], FOLD_2014, embargo_days=-1)


def test_split_fold_reads_timestamp_dates_as_iso_days():
    trade = _t(pd.Timestamp("2014-01-01"), pd.Timestamp("2014-01-09"))
    _, test = folds.split_fold([trade], FOLD_2014, embargo_days=0)
    assert test == [trade]


# --- embargo_days_for -----------------------------------------------------------------------

def test_embargo_days_is_each_horizons_maximum_holding_period():
    assert folds.embargo_days_for("2w") == 14
    assert folds.embargo_days_for("9m") == 270
    for hk in LEGACY_HORIZONS:
        assert folds.embargo_days_for(hk) == HORIZONS[hk]["max_holding_days"]


def test_embargo_days_for_is_the_bar_count_and_documents_it():
    """Partner decision 2 pins the value to max_holding_days, which backtest.py counts in
    trading BARS; used as calendar days it is a lower bound, and the docstrings say so."""
    for hk in HORIZONS:
        assert folds.embargo_days_for(hk) == HORIZONS[hk]["max_holding_days"]
    for fn in (folds.embargo_days_for, folds.split_fold):
        assert "bars" in fn.__doc__ and "lower bound" in fn.__doc__


def test_the_contract_field_is_the_largest_per_horizon_embargo():
    assert V2.embargo_days == max(folds.embargo_days_for(hk) for hk in LEGACY_HORIZONS)


def test_embargo_days_for_refuses_an_unknown_horizon():
    with pytest.raises(ValueError, match="unknown horizon"):
        folds.embargo_days_for("10y")


# --- out_of_fold ------------------------------------------------------------------------------

THREE = dataclasses.replace(V2, fold_test_years=(2014, 2015, 2016))


def _yearly(r_train, r_test):
    """One trade per year 2010..2016: r_train through 2013, r_test after."""
    return [_t(f"{y}-03-02", f"{y}-03-10", r_train if y <= 2013 else r_test)
            for y in range(2010, 2017)]


def _best_mean(train):
    return max(sorted(train), key=lambda c: sum(t.r_multiple for t in train[c])
               / max(len(train[c]), 1))


def test_out_of_fold_selects_on_train_data_only():
    """A shines in train and fails in test; B the reverse. Selection on train
    picks A every fold, so the pooled out-of-fold trades are A's losers."""
    by_config = {"A": _yearly(1.0, -1.0), "B": _yearly(-1.0, 2.0)}
    seen = []

    def select(train):
        seen.append(max(str(t.entry_date)[:10] for trades in train.values() for t in trades))
        return _best_mean(train)

    got = folds.out_of_fold(by_config, folds.anchored_folds(THREE), select, embargo_days=270)
    assert got.choices == ((2014, "A"), (2015, "A"), (2016, "A"))
    assert [t.r_multiple for t in got.trades] == [-1.0, -1.0, -1.0]
    assert seen == ["2013-03-02", "2014-03-02", "2015-03-02"]   # never a test-year trade


def test_out_of_fold_counts_each_trade_once_in_its_own_test_year():
    by_config = {"only": _yearly(1.0, 1.0)}
    got = folds.out_of_fold(by_config, folds.anchored_folds(THREE), _best_mean,
                            embargo_days=270)
    assert _days(got.trades) == ["2014-03-02", "2015-03-02", "2016-03-02"]
    assert len({id(t) for t in got.trades}) == len(got.trades)


def test_out_of_fold_selection_sees_purged_train_data():
    """A config's train trade still open at the test start is invisible to select."""
    straddle = _t("2013-12-20", "2014-01-15", 5.0)
    by_config = {"A": [straddle]}
    seen = []
    folds.out_of_fold(by_config, folds.anchored_folds(THREE)[:1],
                      lambda train: seen.append(train) or "A", embargo_days=270)
    assert seen == [{"A": []}]


def test_out_of_fold_with_no_folds_is_empty():
    assert folds.out_of_fold({"A": _yearly(1.0, 1.0)}, (), _best_mean,
                             embargo_days=0) == OutOfFold(choices=(), trades=[])


def test_out_of_fold_refuses_a_selection_outside_the_configs():
    with pytest.raises(ValueError, match="not one of the configs"):
        folds.out_of_fold({"A": []}, folds.anchored_folds(THREE)[:1], lambda train: "Z",
                          embargo_days=0)


def test_out_of_fold_refuses_overlapping_test_windows():
    overlap = (FOLD_2014, dataclasses.replace(FOLD_2014, test_year=2015,
                                              test_start="2014-12-01", test_end="2015-12-31"))
    with pytest.raises(ValueError, match="overlap"):
        folds.out_of_fold({"A": []}, overlap, lambda train: "A", embargo_days=0)
