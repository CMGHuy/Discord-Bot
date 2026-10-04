from dataclasses import replace

import pandas as pd
import pytest

from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms import dryup_clauses as dryup
from tests.market.structure_fixtures import pullback_frame


def trade(day='2020-01-01', outcome='loss', source='strategy', strategy='RSI'):
    return ArmTrade('T', strategy, '3m', day, outcome,
                    2.0 if outcome == 'win' else -1.0, 2.0, source, 'bullish')


def test_flagged_losers_pass_but_winners_and_empty_flags_fail():
    loser, winner = trade(), trade('2020-01-02', 'win')
    baseline = [loser, winner]
    assert dryup.baseline_mechanism(baseline, {loser.key}, 'strategy').verdict == 'PASS'
    assert dryup.baseline_mechanism(baseline, {winner.key}, 'strategy').verdict == 'FAIL'
    assert dryup.baseline_mechanism(baseline, set(), 'strategy').verdict == 'FAIL'
    assert dryup.baseline_mechanism(baseline, {t.key for t in baseline}, 'strategy').verdict == 'FAIL'


def test_out_of_scope_wins_cannot_inflate_retained():
    removed, retained = trade(), trade('2020-01-02')
    confluence = trade('2020-01-03', 'win', 'confluence')
    macd = trade('2020-01-04', 'win', strategy='MACD')
    assert dryup.baseline_mechanism([removed, retained, confluence, macd],
                                  {removed.key, confluence.key}, 'strategy').verdict == 'FAIL'
    assert dryup.in_scope(confluence, 'confluence')
    assert not dryup.in_scope(macd, 'strategy')
    assert not dryup.in_scope(removed, 'off')


@pytest.mark.parametrize('outcome', ['scratch', 'timeout', 'not_triggered'])
def test_no_decided_group_fails(outcome):
    unknown = replace(trade(), outcome=outcome)
    assert dryup.baseline_mechanism([unknown, trade('2020-01-02', 'win')],
                                  {unknown.key}, 'strategy').verdict == 'FAIL'


def test_flag_boundary_and_empty_none_share():
    ratios = {'none': None, 'equal': .75, 'above': .750001, 'nan': float('nan')}
    assert dryup.flagged_keys(ratios, .75) == {'above'}
    assert dryup.flagged_keys(ratios, 0) == set()
    assert dryup.none_share({}, 'strategy') == {'scope': 'strategy', 'n': 0, 'none': 0, 'share': None}
    assert dryup.none_share(ratios, 'confluence') == {'scope': 'confluence', 'n': 4, 'none': 1, 'share': .25}


def test_scoped_ratios_signal_slice_and_cache():
    frame = pullback_frame()
    early = trade(str(frame.index[2].date()))
    late = trade(str(frame.index[-1].date()))
    confluence = replace(late, source='confluence', strategy='MACD')
    cache = {}
    ratios = dryup.scoped_ratios([early, late, confluence], lambda _: frame, 'strategy', cache)
    assert ratios == {early.key: None, late.key: .5}

    def unavailable(_):
        raise AssertionError('cached ticker loaded again')

    assert dryup.scoped_ratios([early, late], unavailable, 'strategy', cache) == ratios
    assert dryup.scoped_ratios([confluence], lambda _: frame, 'confluence') == {confluence.key: .5}


def test_future_bars_cannot_change_flagged_ratio():
    frame = pullback_frame()
    signal = trade(str(frame.index[-1].date()))
    future = frame.iloc[-1:].copy()
    future.index = pd.DatetimeIndex([frame.index[-1] + pd.Timedelta(days=1)])
    future['Volume'] = 100_000_000
    extended = pd.concat([frame, future])
    ratios = dryup.scoped_ratios([signal], lambda _: extended, 'strategy')
    assert ratios[signal.key] == .5
    assert dryup.flagged_keys(ratios, .4) == {signal.key}


@pytest.mark.parametrize('scope', ['strategy', 'confluence'])
def test_knob_context(scope):
    blob = {'provenance': {'knob_delta': {'PULLBACK_DRYUP_SCOPE': scope,
                                         'PULLBACK_DRYUP_MAX_RATIO': .75}}}
    assert dryup.knob_context(blob) == (scope, .75)


@pytest.mark.parametrize('knobs', [{}, {'PULLBACK_DRYUP_SCOPE': 'off', 'PULLBACK_DRYUP_MAX_RATIO': .75},
                                  {'PULLBACK_DRYUP_SCOPE': 'strategy', 'PULLBACK_DRYUP_MAX_RATIO': 0}])
def test_wrong_knob_context(knobs):
    assert dryup.knob_context({'provenance': {'knob_delta': knobs}}) is None
