import pytest

from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms import pairing


def t(date, outcome="win", r=2.0, direction="bullish", source="strategy", ticker="AAA"):
    return ArmTrade(ticker=ticker, strategy="MACD", horizon_key="3m", entry_date=date,
                    outcome=outcome, r_multiple=r, planned_rr=2.0,
                    source=source, direction=direction)


def test_pre_v100_rows_still_load_and_pair():
    row = {"ticker": "A", "strategy": "MACD", "horizon_key": "3m", "entry_date": "2021-01-04",
           "outcome": "win", "r_multiple": 2.0, "planned_rr": 2.0}
    a, b = ArmTrade(**row), ArmTrade(**row)
    assert a.key == b.key
    assert a.key[-2:] == (None, None)


def test_direction_and_source_separate_keys():
    assert t("2021-01-04", direction="bullish").key != t("2021-01-04", direction="bearish").key
    assert t("2021-01-04", source="strategy").key != t("2021-01-04", source="confluence").key


def test_duplicate_key_raises():
    with pytest.raises(pairing.DuplicateKeyError):
        pairing.index_by_key([t("2021-01-04"), t("2021-01-04")])


def test_identical_arms_change_nothing():
    arm = [t("2021-01-04"), t("2021-01-05", "loss", -1.0)]
    assert pairing.changed_outcomes(arm, list(arm)) == 0


def test_removed_added_and_flipped_each_count():
    base = [t("2021-01-04"), t("2021-01-05", "loss", -1.0), t("2021-01-06")]
    comp = [t("2021-01-04"), t("2021-01-05", "win", 2.0), t("2021-01-07")]
    assert pairing.changed_outcomes(base, comp) == 3


def test_r_change_without_outcome_change_counts():
    assert pairing.changed_outcomes([t("2021-01-04", r=2.0)], [t("2021-01-04", r=1.4)]) == 1


def test_overlap_counts_shared_keys():
    assert pairing.overlap([t("2021-01-04"), t("2021-01-05")], [t("2021-01-05")]) == 1
