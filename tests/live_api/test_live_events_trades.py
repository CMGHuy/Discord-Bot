"""v202 V202-3: activity rows from closed trades and the killswitch."""
from swingbot.admin.api_v1 import live_events as ev

CLOSED = "2026-10-29T15:20:00+00:00"


def _trade(**over):
    trade = {"id": "812", "ticker": "NVDA", "direction": "bullish", "status": "win",
             "entry": 100.0, "stop_loss": 95.0, "opened_at": "2026-10-20T08:00:00+00:00",
             "closed_at": CLOSED, "realized_pnl_amount": 441.0,
             "legs": [{"fraction": 0.5, "exit_price": 105.0, "r": 1.0, "reason": "tp1"},
                      {"fraction": 0.5, "exit_price": 116.0, "r": 3.2,
                       "reason": "tp1_runner_tp2"}]}
    return {**trade, **over}


def test_a_scaled_out_win():
    [row] = ev.trade_closed_rows([_trade()])
    assert row == {"at": CLOSED, "kind": "trade_closed", "text": "NVDA closed · TP2",
                   "tone": "positive", "ref": "812", "pnl": {"r": 2.1, "amount": 441.0}}


def test_a_single_exit_loss_without_an_amount():
    trade = _trade(ticker="AAPL", status="loss", legs=None, exit_price=95.0,
                   realized_pnl_amount=None)
    [row] = ev.trade_closed_rows([trade])
    assert row["text"] == "AAPL closed · loss"
    assert row["tone"] == "negative"
    assert row["pnl"] == {"r": -1.0, "amount": None}


def test_a_manual_close_has_no_r():
    trade = _trade(ticker="AAPL", status="closed", legs=None, close_reason="manual",
                   realized_pnl_amount=None)
    [row] = ev.trade_closed_rows([trade])
    assert row["text"] == "AAPL closed · manual"
    assert (row["tone"], row["pnl"]) == ("neutral", None)


def test_outcome_labels_from_the_last_leg():
    for reason, label in (("tp1_runner_be", "runner at floor"), ("tp1_runner_trail", "trailed"),
                          ("time_exit", "time exit"), ("scratch", "scratch"), ("loss", "stop")):
        legs = [{"fraction": 1.0, "exit_price": 100.0, "r": 0.0, "reason": reason}]
        assert ev.trade_closed_rows([_trade(legs=legs)])[0]["text"] == f"NVDA closed · {label}"


def test_open_trades_and_missing_times_yield_nothing():
    """opened_at is the alert time: an open trade never becomes a row."""
    assert ev.trade_closed_rows([_trade(status="open", closed_at=None)]) == []
    assert ev.trade_closed_rows([_trade(closed_at=None)]) == []
    assert ev.trade_closed_rows([]) == []


def test_killswitch_engaged_and_released_wording():
    on = {"on": True, "reason": "daily loss", "at": "2026-10-29T07:31:00+00:00"}
    off = {"on": False, "reason": None, "at": "2026-10-29T09:00:00+00:00", "manual_release": True}
    assert ev.killswitch_rows(on) == [{"at": "2026-10-29T07:31:00+00:00", "kind": "killswitch",
                                       "text": "Killswitch engaged", "tone": "warning",
                                       "ref": None, "pnl": None}]
    [released] = ev.killswitch_rows(off)
    assert (released["text"], released["tone"]) == ("Killswitch released", "neutral")


def test_a_killswitch_with_no_transition_yields_nothing():
    assert ev.killswitch_rows({"on": False, "reason": None, "at": None}) == []
    assert ev.killswitch_rows(None) == []
