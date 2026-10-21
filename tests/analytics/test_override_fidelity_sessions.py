"""v173 §3: override sessions, plan readers, stamp kinds and the OverrideRow shape.

Dates: 2026-10-01 is a Thursday in EDT (UTC-4); 2026-11-26 is Thanksgiving,
2026-11-27 a 13:00 ET early close and 2026-12-01 a Tuesday in EST (UTC-5).
"""
import dataclasses
import datetime as dt

import pandas as pd
import pytest

from swingbot.core.analytics import override_fidelity as of
from swingbot.core.backtesting.instrument import stats
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2

U = dt.timezone.utc
FILL_AT = "2026-10-01T14:00:00+00:00"    # Thu 10:00 ET
TP1_AT = "2026-10-05T15:00:00+00:00"     # Mon 11:00 ET
CLOSE_AT = "2026-10-07T18:00:00+00:00"   # Wed 14:00 ET
#: A post-v173 stamp from a live quote (the V173-3 shape).
QUOTE_STAMP = {"exit_price": 104.0, "price_source": "quote", "quote_ts": CLOSE_AT,
               "bars_asof": "2026-10-06"}

ROW_KEYS = ("plan_id", "ticker", "horizon", "direction", "state_at_close", "close_date",
            "bulk", "approx", "price_source", "status", "actual_r", "engine_r", "delta_r",
            "delta_r_gross", "actual_usd", "engine_usd", "delta_usd", "engine_exit_reason",
            "outcome", "source")


def override_plan(*, reason="manual", partial=False, status=PlanStatus.CLOSED,
                  history=None, close_at=CLOSE_AT, override=None, **kw):
    """A live plan record closed by a manual override (shared by the v173 tests).

    `override` is the stamp dict put on the CLOSED entry; leave it None for a
    pre-v173 close (the key is then absent). A failed post-v173 stamp
    (`"override": None`) needs an explicit `history`."""
    if history is None:
        history = [{"status": "ACTIVE", "reason": "filled", "at": FILL_AT}]
        if partial:
            history.append({"status": "PARTIAL", "reason": "tp1_partial", "at": TP1_AT})
        closed = {"status": "CLOSED", "reason": reason, "at": close_at}
        if override is not None:
            closed["override"] = override
        history.append(closed)
    legs = ([{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1",
              "closed_at": TP1_AT}] if partial else [])
    base = dict(
        plan_id="p1", ticker="T", created_at="2026-09-30", source="strategy",
        strategy="Probe", horizon_key="4w", direction="bullish", entry_type="market",
        trigger_price=100.0, entry_price=100.0, expiry_bars=3, stop_loss=95.0, tp1=110.0,
        tp1_fraction=0.5 if partial else 1.0, tp2=120.0 if partial else None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=1.0, quality_score=0,
        quality_breakdown=[], badge="WEAK", badge_stats={}, status=status,
        status_history=history, legs_realized=legs,
    )
    base.update(kw)
    return TradePlanV2(**base)


# --- frozen constants --------------------------------------------------------

def test_the_frozen_constants():
    assert of.MANUAL_REASONS == ("manual", "manual_bulk")
    assert of.STATUSES == ("resolved", "open", "unstamped", "stale", "ambiguous",
                           "parity_mismatch", "split_affected", "unreplayable")
    assert of.EXCLUDED_STATUSES == ("unstamped", "stale", "ambiguous", "parity_mismatch",
                                    "split_affected", "unreplayable")
    assert of.EXCLUDED_STATUSES == tuple(s for s in of.STATUSES if s not in ("resolved", "open"))
    assert of.TIMEOUT_REASONS == ("timeout", "runner_timeout")
    assert of.STAMP_KINDS == ("missing", "failed", "stamped")
    assert (of.DEAD_BAND, of.VERDICT_FLOOR, of.WEEK_FLOOR, of.EXCLUDED_CAP,
            of.SPLIT_TOLERANCE) == (0.05, 30, 10, 0.20, 0.02)
    assert of.LEDGER_ID == "v173-override-fidelity"
    assert of.ROW_FIELDS == ROW_KEYS


# --- assign_session: one test per row of the §3 table ------------------------

@pytest.mark.parametrize("at, session, kind", [
    ("2026-10-01T13:00:00+00:00", dt.date(2026, 10, 1), "open"),    # 09:00 ET, before the open
    ("2026-10-01T13:29:59+00:00", dt.date(2026, 10, 1), "open"),    # 09:29:59 ET
    ("2026-10-01T13:30:00+00:00", dt.date(2026, 10, 1), "close"),   # 09:30 ET, the open itself
    ("2026-10-01T18:00:00+00:00", dt.date(2026, 10, 1), "close"),   # regular hours
    ("2026-10-01T22:00:00+00:00", dt.date(2026, 10, 1), "close"),   # 18:00 ET, after the close
    ("2026-12-01T14:00:00+00:00", dt.date(2026, 12, 1), "open"),    # 09:00 EST
    ("2026-12-01T14:30:00Z", dt.date(2026, 12, 1), "close"),        # 09:30 EST, Z suffix
    ("2026-11-27T14:00:00+00:00", dt.date(2026, 11, 27), "open"),   # early-close day, pre-open
    ("2026-11-27T19:00:00+00:00", dt.date(2026, 11, 27), "close"),  # 14:00 EST, after the 13:00 close
])
def test_a_session_day(at, session, kind):
    assert of.assign_session(at) == of.SessionHit(session, kind)


def test_the_utc_date_is_not_the_et_date():
    """02:30 UTC on Oct 2 is 22:30 ET on Oct 1: Oct 1's close, not Oct 2's open."""
    assert of.assign_session("2026-10-02T02:30:00+00:00") == of.SessionHit(
        dt.date(2026, 10, 1), "close")


@pytest.mark.parametrize("at, session", [
    ("2026-10-03T15:00:00+00:00", dt.date(2026, 10, 2)),   # Saturday -> Friday
    ("2026-10-05T03:00:00+00:00", dt.date(2026, 10, 2)),   # Sunday 23:00 ET (Monday in UTC)
    ("2026-11-26T15:00:00+00:00", dt.date(2026, 11, 25)),  # Thanksgiving -> Wednesday
])
def test_a_non_trading_day_takes_the_last_session_close(at, session):
    assert of.assign_session(at) == of.SessionHit(session, "close")


def test_a_naive_timestamp_is_read_as_utc():
    assert of.assign_session("2026-10-01T13:00:00") == of.SessionHit(dt.date(2026, 10, 1), "open")


@pytest.mark.parametrize("at", [None, "", "garbage", "2017-06-01T15:00:00+00:00",
                                "2031-01-02T15:00:00+00:00"])
def test_no_session_for_missing_unparseable_or_out_of_calendar(at):
    assert of.assign_session(at) is None


# --- latest_completed_session ------------------------------------------------

@pytest.mark.parametrize("now, expected", [
    (dt.datetime(2026, 10, 1, 19, 59, tzinfo=U), dt.date(2026, 9, 30)),   # 15:59 ET: still open
    (dt.datetime(2026, 10, 1, 20, 0, tzinfo=U), dt.date(2026, 10, 1)),    # 16:00 ET: closed
    (dt.datetime(2026, 10, 3, 12, 0, tzinfo=U), dt.date(2026, 10, 2)),    # Saturday
    (dt.datetime(2026, 10, 5, 13, 0, tzinfo=U), dt.date(2026, 10, 2)),    # Monday pre-open
    (dt.datetime(2026, 11, 27, 18, 0, tzinfo=U), dt.date(2026, 11, 27)),  # 13:00 EST early close
    (dt.datetime(2026, 11, 27, 17, 59, tzinfo=U), dt.date(2026, 11, 25)), # before it; 26th a holiday
    (dt.datetime(2026, 10, 1, 20, 0), dt.date(2026, 10, 1)),              # naive = UTC
])
def test_latest_completed_session(now, expected):
    assert of.latest_completed_session(now) == expected


def test_latest_completed_session_refuses_outside_the_calendar():
    with pytest.raises(ValueError):
        of.latest_completed_session(dt.datetime(2017, 6, 1, tzinfo=U))


# --- session_index -----------------------------------------------------------

def _frame(days):
    idx = pd.DatetimeIndex(days)
    ones = [1.0] * len(idx)
    return pd.DataFrame({"Open": ones, "High": ones, "Low": ones, "Close": ones,
                         "Volume": ones}, index=idx)


def test_session_index_finds_the_bar_by_date():
    df = _frame(["2026-10-01", "2026-10-02", "2026-10-05"])
    assert of.session_index(df, dt.date(2026, 10, 5)) == 2
    assert of.session_index(df, dt.date(2026, 10, 1)) == 0


def test_session_index_is_none_for_a_missing_day_or_no_bars():
    df = _frame(["2026-10-01", "2026-10-02", "2026-10-05"])
    assert of.session_index(df, dt.date(2026, 10, 3)) is None
    assert of.session_index(df, None) is None
    assert of.session_index(None, dt.date(2026, 10, 5)) is None
    assert of.session_index(df.iloc[0:0], dt.date(2026, 10, 5)) is None


# --- plan readers --------------------------------------------------------------

def test_transition_at_reads_the_first_entry_with_the_status():
    plan = override_plan(partial=True)
    assert of.transition_at(plan, "ACTIVE") == FILL_AT
    assert of.transition_at(plan, "PARTIAL") == TP1_AT
    assert of.transition_at(plan, "CLOSED") == CLOSE_AT
    assert of.transition_at(override_plan(), "PARTIAL") is None


@pytest.mark.parametrize("reason", ["manual", "manual_bulk"])
def test_a_manual_close_is_an_override(reason):
    plan = override_plan(reason=reason)
    assert of.override_entry(plan) == plan.status_history[-1]
    assert of.is_override(plan)


def test_an_engine_close_is_not_an_override():
    plan = override_plan(reason="tp1_runner_trail", partial=True)
    assert of.override_entry(plan) is None and not of.is_override(plan)


def test_only_the_last_entry_counts():
    """A manual reason earlier in the history (never the terminal one) is not an override."""
    history = [{"status": "ACTIVE", "reason": "manual", "at": FILL_AT},
               {"status": "CLOSED", "reason": "stop", "at": CLOSE_AT}]
    plan = override_plan(history=history)
    assert not of.is_override(plan)


def test_an_open_or_empty_plan_is_not_an_override():
    active = override_plan(status=PlanStatus.ACTIVE,
                           history=[{"status": "ACTIVE", "reason": "filled", "at": FILL_AT}])
    assert not of.is_override(active)
    assert not of.is_override(override_plan(history=[]))


def test_state_at_close():
    assert of.state_at_close(override_plan(partial=True)) == "PARTIAL"
    assert of.state_at_close(override_plan()) == "ACTIVE"


# --- stamp_kind: missing, failed, stamped --------------------------------------

def _closed(**extra):
    return {"status": "CLOSED", "reason": "manual", "at": CLOSE_AT, **extra}


def test_no_override_key_is_a_pre_v173_close():
    assert of.stamp_kind(_closed()) == "missing"
    assert of.stamp_kind(of.override_entry(override_plan())) == "missing"


def test_no_entry_at_all_is_missing():
    assert of.stamp_kind(None) == "missing"
    assert of.stamp_kind({}) == "missing"


def test_a_stamp_that_failed_to_build_is_failed():
    assert of.stamp_kind(_closed(override=None)) == "failed"


def test_a_stamp_with_no_price_is_failed():
    stamp = {"exit_price": None, "price_source": "none", "quote_ts": None, "bars_asof": None}
    assert of.stamp_kind(_closed(override=stamp)) == "failed"


def test_a_garbled_stamp_is_failed_not_stamped():
    assert of.stamp_kind(_closed(override="104.0")) == "failed"


@pytest.mark.parametrize("source", ["quote", "bar_close"])
def test_a_priced_stamp_is_stamped(source):
    stamp = {**QUOTE_STAMP, "price_source": source}
    if source == "bar_close":
        stamp["quote_ts"] = None
    assert of.stamp_kind(_closed(override=stamp)) == "stamped"
    plan = override_plan(override=stamp)
    assert of.stamp_kind(of.override_entry(plan)) == "stamped"


def test_the_kind_is_read_from_the_key_alone_never_the_reason_or_the_date():
    """A bulk close, or a close dated after v173 shipped, with no key is still
    'missing': nothing is inferred (no read-time upcasting)."""
    late = _closed(reason="manual_bulk", at="2026-12-01T18:00:00+00:00")
    assert of.stamp_kind(late) == "missing"


# --- OverrideRow -------------------------------------------------------------

def _row(**kw):
    base = dict(plan_id="p1", ticker="T", horizon="4w", direction="bullish",
                state_at_close="ACTIVE", close_date=dt.date(2026, 10, 7), bulk=False,
                approx=False, price_source="quote", status="resolved")
    base.update(kw)
    return of.OverrideRow(**base)


def test_row_fields_are_exactly_the_payload_keys_in_order():
    assert tuple(f.name for f in dataclasses.fields(of.OverrideRow)) == ROW_KEYS
    assert len(ROW_KEYS) == 20


def test_row_defaults():
    row = _row()
    assert row.source == "manual"
    assert all(getattr(row, key) is None for key in ROW_KEYS[10:19])


def test_to_dict_writes_the_close_date_as_iso():
    row = _row(actual_r=0.5, engine_r=0.2, delta_r=0.3, delta_r_gross=0.35, outcome="helped")
    body = row.to_dict()
    assert tuple(body) == ROW_KEYS
    assert body["close_date"] == "2026-10-07"
    assert body["delta_r"] == 0.3 and body["delta_r_gross"] == 0.35
    assert body["outcome"] == "helped"
    assert _row(close_date=None).to_dict()["close_date"] is None


def test_an_unstamped_row_carries_no_figures():
    row = _row(status="unstamped", price_source="none")
    body = row.to_dict()
    assert body["status"] == "unstamped"
    assert all(body[key] is None for key in ("actual_r", "engine_r", "delta_r", "delta_r_gross",
                                             "actual_usd", "engine_usd", "delta_usd"))


def test_entry_date_is_the_close_date_for_week_clustering():
    row = _row()
    assert row.entry_date == dt.date(2026, 10, 7)
    assert stats.iso_week_key(row.entry_date) == "2026-W41"
    assert list(stats.group_by_week([row])) == ["2026-W41"]


def test_row_is_frozen_and_refuses_an_unknown_status():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _row().status = "open"
    with pytest.raises(ValueError):
        _row(status="timeout")


@pytest.mark.parametrize("status", ["resolved", "open", "unstamped", "stale", "ambiguous",
                                    "parity_mismatch", "split_affected", "unreplayable"])
def test_every_status_is_accepted(status):
    assert _row(status=status).status == status


# --- outcome_of: the frozen ±0.05R dead band ----------------------------------

@pytest.mark.parametrize("delta, outcome", [
    (0.051, "helped"), (0.05, "neutral"), (0.0, "neutral"), (-0.05, "neutral"),
    (-0.051, "hurt"), (2.0, "helped"), (-1.3, "hurt"), (None, None),
])
def test_outcome_of(delta, outcome):
    assert of.outcome_of(delta) == outcome
