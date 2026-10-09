"""v144: the scope's origin filter -- default regular, a named cohort on request."""
import pytest

from swingbot.core.analytics.scope import BookScope, ScopeError, echo, parse_scope, select


def _t(trade_id, origin=None, ledger=None):
    t = {"id": trade_id, "status": "win", "closed_at": "2026-08-04T15:00:00+00:00",
         "strategy": "MACD", "horizon_key": "2w", "direction": "bullish",
         "target_sources": ["MACD"]}
    if origin:
        t["origin"] = origin
    if ledger:
        t["ledger"] = ledger
    return t


BOOK = [_t("r"), _t("w", ledger="weak"), _t("o", origin="next_session"),
        _t("ow", origin="next_session", ledger="weak")]


def test_default_scope_is_the_regular_lane():
    assert parse_scope({}).origin is None
    assert [t["id"] for t in select(BOOK, parse_scope({}))] == ["r"]
    assert [t["id"] for t in select(BOOK, parse_scope({"ledger": "both"}))] == ["r", "w"]


def test_a_named_cohort_selects_only_it():
    scope = parse_scope({"origin": "next_session", "ledger": "both"})
    assert [t["id"] for t in select(BOOK, scope)] == ["o", "ow"]


def test_an_unknown_origin_is_rejected():
    with pytest.raises(ScopeError, match="origin must be one of"):
        parse_scope({"origin": "regular"})


def test_echo_adds_origin_only_when_set():
    assert "origin" not in echo(BookScope(), 0)["scope"]
    assert echo(BookScope(origin="next_session"), 2)["scope"]["origin"] == "next_session"
