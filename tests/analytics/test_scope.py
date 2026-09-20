import pytest

from swingbot.core.analytics.scope import (
    BookScope, ScopeError, closed_only, echo, parse_scope, reject_unknown, select,
)


def _t(status="win", closed_at="2026-08-04T15:00:00+00:00", ledger=None, strategy="MACD",
       horizon="2w", direction="bullish", source="strategy"):
    t = {"id": f"{strategy}-{horizon}-{closed_at}", "status": status, "closed_at": closed_at,
         "strategy": strategy, "horizon_key": horizon, "direction": direction, "source": source,
         "entry": 100.0, "stop_loss": 95.0, "exit_price": 104.0, "target_sources": [strategy]}
    if ledger is not None:
        t["ledger"] = ledger
    return t


def test_parse_defaults_to_main_ledger_and_open_bounds():
    s = parse_scope({})
    assert s == BookScope(start=None, end=None, ledger="main", strategy=None, horizon=None, direction=None)


def test_parse_reads_every_param():
    s = parse_scope({"from": "2026-08-01", "to": "2026-08-31", "ledger": "both",
                     "strategy": "MACD", "horizon": "2w", "direction": "bearish"})
    assert (s.start, s.end, s.ledger, s.strategy, s.horizon, s.direction) == \
        ("2026-08-01", "2026-08-31", "both", "MACD", "2w", "bearish")


@pytest.mark.parametrize("args,fragment", [
    ({"from": "last-tuesday"}, "from must be a YYYY-MM-DD date"),
    ({"from": "2026-09-01", "to": "2026-08-01"}, "from must not be after to"),
    ({"ledger": "shadow"}, "ledger must be one of"),
    ({"direction": "long"}, "direction must be one of"),
    ({"horizon": "3y"}, "horizon must be one of"),
])
def test_parse_rejects_bad_values(args, fragment):
    with pytest.raises(ScopeError, match=fragment):
        parse_scope(args)


def test_reject_unknown_names_the_first_offender_and_allows_extras():
    reject_unknown({"from": "2026-08-01", "dim": "strategy"}, extra=("dim",))
    with pytest.raises(ScopeError, match="unknown parameter 'zzz'"):
        reject_unknown({"zzz": "1"})


def test_closed_only_keeps_win_loss_closed():
    trades = [_t("win"), _t("loss"), _t("closed"), _t("open", closed_at=None)]
    assert [t["status"] for t in closed_only(trades)] == ["win", "loss", "closed"]


def test_select_applies_every_field():
    closed = [
        _t(closed_at="2026-07-30T10:00:00+00:00"),                  # out of range
        _t(ledger="weak"),                                           # wrong ledger
        _t(strategy="Volume Profile"),                               # wrong strategy
        _t(horizon="4w"),                                            # wrong horizon
        _t(direction="bearish"),                                     # wrong direction
        _t(),                                                        # the one survivor
    ]
    scope = parse_scope({"from": "2026-08-01", "to": "2026-08-31", "strategy": "MACD",
                         "horizon": "2w", "direction": "bullish"})
    assert len(select(closed, scope)) == 1


def test_select_ledger_missing_means_main_and_both_keeps_all():
    closed = [_t(), _t(ledger="main"), _t(ledger="weak")]
    assert len(select(closed, parse_scope({}))) == 2
    assert len(select(closed, parse_scope({"ledger": "weak"}))) == 1
    assert len(select(closed, parse_scope({"ledger": "both"}))) == 3


def test_echo_shape():
    body = echo(parse_scope({"strategy": "MACD"}), 7)
    assert body == {"scope": {"from": None, "to": None, "ledger": "main", "strategy": "MACD",
                              "horizon": None, "direction": None}, "n": 7}
