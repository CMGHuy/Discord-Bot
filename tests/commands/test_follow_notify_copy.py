"""Follower updates report paper-plan facts across every event and direction."""
import datetime as dt

import pytest

from swingbot import config
from swingbot.commands.scanning import follow_notify as fn
from swingbot.core import presentation as ui
from swingbot.core.presentation.kinds import Kind
from tests.scanning.test_embeds_v3 import make_plan_v2


FORBIDDEN = (
    "exit now", "move stop", "move your stop", "take profit", "sell now",
    "buy now", "close your", "you should",
)

CASES = [
    ('near_stop', 'near_stop', 'ACTIVE', {'r_dist': .21, 'price': 96.05},
     'is 0.21R from its stop, last 96.05.', Kind.NEAR_STOP),
    ('tp1', 'tp1_partial', 'PARTIAL', {'exit_price': 110},
     'reached TP1 at 110.00.', Kind.TP1_HIT),
    ('tp1', 'closed', 'CLOSED', {'reason': 'win', 'exit_price': 110},
     'closed at TP1 110.00: +2.0R.', Kind.TP1_HIT),
    ('tp2', 'closed', 'CLOSED', {'reason': 'tp1_runner_tp2', 'exit_price': 120},
     'closed at TP2 120.00: +4.0R.', Kind.WIN),
    ('stopped', 'closed', 'CLOSED', {'reason': 'loss', 'exit_price': 95},
     'closed at its stop 95.00: −1.0R.', Kind.STOPPED),
    ('stopped', 'closed', 'CLOSED', {'reason': 'scratch', 'exit_price': 100},
     'closed at breakeven 100.00: 0.0R.', Kind.STOPPED),
    ('stopped', 'closed', 'CLOSED', {'reason': 'tp1_runner_be', 'exit_price': 105},
     'closed at its runner stop 105.00: +1.0R.', Kind.STOPPED),
    ('stopped', 'closed', 'CLOSED', {'reason': 'tp1_runner_trail', 'exit_price': 108},
     'closed at its trailing stop 108.00: +1.6R.', Kind.STOPPED),
    ('expired', 'cancelled_expired', 'CANCELLED', {}, 'expired unfilled.', Kind.EXPIRED),
    ('closed_other', 'closed', 'CLOSED', {'reason': 'time_exit', 'exit_price': 102},
     'closed by time exit at 102.00: +0.4R.', Kind.EXITED),
    ('closed_other', 'closed', 'CLOSED', {'reason': 'stall_exit', 'exit_price': 102},
     'closed by stall exit at 102.00: +0.4R.', Kind.EXITED),
    ('closed_other', 'closed', 'CLOSED', {'reason': 'tp1_runner_progress_stall', 'exit_price': 102},
     'closed by structure exit at 102.00: +0.4R.', Kind.EXITED),
    ('closed_other', 'closed', 'CLOSED', {'reason': 'custom_exit', 'exit_price': 102},
     'closed by custom exit at 102.00: +0.4R.', Kind.EXITED),
    ('closed_other', 'cancelled_invalidated', 'CANCELLED', {},
     'cancelled: invalidated before entry.', Kind.INVALIDATED),
    ('closed_other', 'cancelled_risk_cap', 'CANCELLED', {},
     'cancelled: risk cap reached.', Kind.RISK_CAP),
]


def _plan(status='ACTIVE', direction='bullish'):
    plan = make_plan_v2(direction=direction, plan_id='12345678-1234-4234-8234-123456789abc')
    plan.status = status
    plan.working_stop = 101 if status == 'PARTIAL' else 95
    return plan


@pytest.mark.parametrize('event,transition,status,detail,phrase,kind', CASES)
def test_event_copy_reports_the_event_and_current_open_levels(event, transition, status, detail, phrase, kind):
    plan = _plan(status)
    line = fn.message_line(plan, event, transition, detail)
    expected = 'Paper plan update: NVDA long ' + phrase
    if status in {'ACTIVE', 'PARTIAL'}:
        stop, target = ('95.00', '110.00') if status == 'ACTIVE' else ('101.00', '120.00')
        expected += f' Stop now at {stop}, remaining target {target}.'
    assert line == expected


@pytest.mark.parametrize('direction,side', [('bullish', 'long'), ('bearish', 'short')])
@pytest.mark.parametrize('event,transition,status,detail,phrase,kind', CASES)
def test_rendered_updates_are_factual_linked_and_registry_styled(monkeypatch, direction, side, event, transition, status, detail, phrase, kind):
    monkeypatch.setattr(config, 'ADMIN_PUBLIC_URL', 'https://example.com')
    plan = _plan(status, direction)
    embed = fn.build_notify_embed(plan, event, transition, detail)
    payload = embed.to_dict()
    assert isinstance(embed, ui.PushEmbed)
    assert embed.kind is kind
    assert ui.push_kwargs(embed)['content'] == embed.description
    assert f'NVDA {side} ' in embed.push_text
    assert payload['url'] == f'https://example.com/plans/{plan.plan_id}'
    assert embed.footer.text.endswith(' · Paper plan update, not advice. R is before costs and tax.')
    rendered = str(payload).lower() + embed.push_text.lower()
    for forbidden in FORBIDDEN:
        assert forbidden not in rendered


def test_retried_near_stop_copy_identifies_the_observation_time():
    plan = _plan('CLOSED')
    detail = {'r_dist': .21, 'price': 96.05,
              'observed_at': dt.datetime(2026, 10, 12, 14, 5, tzinfo=dt.timezone.utc)}
    line = fn.message_line(plan, 'near_stop', 'near_stop', detail)
    assert 'was 0.21R from its stop at 2026-10-12 14:05 UTC, last observed 96.05.' in line
    assert 'Stop now at' not in line


@pytest.mark.parametrize('status,target', [('ACTIVE', '110.00'), ('PARTIAL', '120.00')])
def test_near_stop_uses_current_resting_stop_in_both_open_states(status, target):
    plan = _plan(status)
    plan.working_stop = 103
    assert fn.message_line(plan, 'near_stop', 'near_stop', {'r_dist': .21, 'price': 104}).endswith(
        f'Stop now at 103.00, remaining target {target}.')


def test_missing_prices_and_targets_use_the_shared_absent_format():
    plan = _plan('PARTIAL')
    plan.tp1 = None
    plan.tp2 = None
    line = fn.message_line(plan, 'tp1', 'tp1_partial', {})
    assert f'reached TP1 at {ui.ABSENT}.' in line
    assert line.endswith(f'remaining target {ui.ABSENT}.')


@pytest.mark.parametrize('direction,exit_price', [('bullish', 110), ('bearish', 90)])
def test_close_r_uses_position_direction(direction, exit_price):
    plan = _plan('CLOSED', direction)
    assert fn.message_line(plan, 'tp1', 'closed', {'exit_price': exit_price}).endswith('+2.0R.')


def test_close_r_uses_fraction_weighted_realized_legs():
    plan = _plan('CLOSED')
    plan.legs_realized = [{'fraction': .5, 'r': 2}, {'fraction': .5, 'r': 4}]
    assert fn.message_line(plan, 'tp2', 'closed', {'exit_price': 120}).endswith('+3.0R.')


@pytest.mark.parametrize('exit_price', [100, 99.999999, 100.000001])
def test_close_r_normalizes_rounded_zero(exit_price):
    plan = _plan('CLOSED')
    assert fn.message_line(plan, 'stopped', 'closed', {'reason': 'scratch', 'exit_price': exit_price}).endswith('0.0R.')


def test_fallback_cancellation_remains_factual():
    assert fn.message_line(_plan('CANCELLED'), 'closed_other', 'cancelled_other', {}) == (
        'Paper plan update: NVDA long cancelled: withdrawn before entry.')


def test_copy_table_covers_the_notify_events():
    assert set(fn.COPY) == set(fn.NOTIFY_EVENTS)
    assert fn.FORBIDDEN_PHRASES == FORBIDDEN


def test_next_notification_reads_reloaded_public_url(monkeypatch):
    plan = _plan()
    monkeypatch.setattr(config, 'ADMIN_PUBLIC_URL', '')
    before = fn.build_notify_embed(plan, 'near_stop', 'near_stop', {'r_dist': .21, 'price': 96})
    monkeypatch.setattr(config, 'ADMIN_PUBLIC_URL', 'https://new.example.com')
    after = fn.build_notify_embed(plan, 'near_stop', 'near_stop', {'r_dist': .21, 'price': 96})
    assert 'url' not in before.to_dict()
    assert after.url == f'https://new.example.com/plans/{plan.plan_id}'


@pytest.mark.parametrize('direction,fill,target', [('bullish', 111, 110), ('bearish', 89, 90)])
def test_tp1_partial_reports_the_realized_leg_fill(direction, fill, target):
    plan = _plan('PARTIAL', direction)
    plan.tp1 = target
    detail = {'fraction': .5, 'exit_price': fill, 'r': 2.2, 'reason': 'tp1',
              'closed_at': '2026-10-12T14:00:00Z'}
    embed = fn.build_notify_embed(plan, 'tp1', 'tp1_partial', detail)
    assert f'reached TP1 at {fill:.2f}.' in embed.description
    assert embed.push_text == embed.description


@pytest.mark.parametrize('direction,target', [('bullish', 110), ('bearish', 90)])
def test_tp1_partial_falls_back_to_the_plan_target(direction, target):
    plan = _plan('PARTIAL', direction)
    plan.tp1 = target
    assert f'reached TP1 at {target:.2f}.' in fn.message_line(plan, 'tp1', 'tp1_partial', {})
