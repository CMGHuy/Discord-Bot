"""GET /api/v1/market/tape -- the Lane B feed."""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture(autouse=True)
def no_daily_batch_network(monkeypatch):
    """`change_pct` is priced off `get_daily_data_batch`'s ONE batched fetch
    (see `tape()` in swingbot/admin/api_v1/market.py), not a per-symbol
    `_ohlcv_frame` call -- that per-symbol version is exactly the uncached
    2-year-per-request bug this endpoint was fixed to stop doing. Stubbed
    here so every test defaults to "no frame" (change_pct stays None) unless
    it overrides this to exercise the real computation."""
    monkeypatch.setattr("swingbot.core.marketdata.data.get_daily_data_batch", lambda syms: {})


def _frame(prev_close: float, last_close: float) -> pd.DataFrame:
    """A minimal 2-row OHLCV frame -- only `Close` matters to `_tape_change_pct`."""
    idx = pd.bdate_range("2026-01-01", periods=2)
    return pd.DataFrame({"Close": [prev_close, last_close]}, index=idx)


def test_tape_empty_symbols_returns_no_rows(logged_in):
    resp = logged_in.get("/api/v1/market/tape?symbols=")
    assert resp.status_code == 200
    assert resp.get_json()["rows"] == []


def test_tape_prices_only_requested_symbols(logged_in):
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={"NVDA": 182.4}) as batch:
        resp = logged_in.get("/api/v1/market/tape?symbols=NVDA")
    assert resp.status_code == 200
    body = resp.get_json()
    assert [r["symbol"] for r in body["rows"]] == ["NVDA"]
    assert body["rows"][0]["price"] == 182.4
    # The endpoint must never price the whole watchlist.
    assert batch.call_args[0][0] == ["NVDA"]


def test_tape_prices_are_one_batched_call_not_one_per_symbol(logged_in):
    """The regression this whole fix round exists for: N symbols must cost
    ONE `get_daily_data_batch` call, never N per-symbol OHLCV fetches."""
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={}), \
         patch("swingbot.core.marketdata.data.get_daily_data_batch",
               return_value={}) as batch:
        logged_in.get("/api/v1/market/tape?symbols=NVDA,AMD,AAPL")
    assert batch.call_count == 1
    assert batch.call_args[0][0] == ["NVDA", "AMD", "AAPL"]


def test_tape_symbols_are_deduped_uppercased_and_capped(logged_in):
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={}) as batch:
        logged_in.get("/api/v1/market/tape?symbols=nvda,NVDA,amd")
    assert batch.call_args[0][0] == ["NVDA", "AMD"]


def test_tape_symbol_cap_is_actually_enforced_on_the_response(logged_in):
    """Named for the 40-symbol cap and previously never actually checking it:
    the earlier test above only asserts what `_tape_symbols` passes on to the
    price batch, not what the response itself contains."""
    symbols = ",".join(f"SYM{i}" for i in range(45))
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={}):
        body = logged_in.get(f"/api/v1/market/tape?symbols={symbols}").get_json()
    assert len(body["rows"]) == 40
    assert [r["symbol"] for r in body["rows"]] == [f"SYM{i}" for i in range(40)]


def test_tape_change_pct_is_computed_from_the_previous_close(logged_in):
    """The actual computed value, not just "is it None" -- `change_pct`
    itself was never asserted before this fix round."""
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={"NVDA": 110.0}), \
         patch("swingbot.core.marketdata.data.get_daily_data_batch",
               return_value={"NVDA": _frame(prev_close=100.0, last_close=105.0)}):
        row = logged_in.get("/api/v1/market/tape?symbols=NVDA").get_json()["rows"][0]
    # (110.0 - 100.0) / 100.0 * 100 == 10.0 -- uses the FRAME's previous close
    # (100.0), not its own last close (105.0), and the live `price` (110.0),
    # matching _tape_change_pct's contract exactly.
    assert row["change_pct"] == 10.0


def test_tape_open_position_outranks_plan(logged_in):
    # "direction" is always present on a real logged trade (TradeLog.log_trade
    # always writes it) -- included here so this fixture matches that shape
    # now that the R-multiple sign depends on it.
    trades = [{"ticker": "NVDA", "status": "open", "direction": "bullish",
               "entry": 170.0, "stop_loss": 160.0}]
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={"NVDA": 182.0}), \
         patch("swingbot.core.tracking.performance.TradeLog.get_trades",
               return_value=trades):
        row = logged_in.get("/api/v1/market/tape?symbols=NVDA").get_json()["rows"][0]
    assert row["context_kind"] == "position"
    assert row["sort_rank"] == 0
    assert row["context_label"] == "+1.2R"


def test_tape_bearish_position_r_multiple_sign_is_correct(logged_in):
    """A short that has moved AGAINST it (price above entry) is a loser.

    Regression test: `_tape_context` used to compute the R-multiple with no
    direction sign at all, so a losing short rendered as a winning "+R" --
    the same sign convention `tracking/performance.py` already applies
    everywhere else (e.g. `closed_r_multiple`) must hold here too.
    """
    trades = [{"ticker": "NVDA", "status": "open", "direction": "bearish",
               "entry": 170.0, "stop_loss": 180.0}]
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={"NVDA": 175.0}), \
         patch("swingbot.core.tracking.performance.TradeLog.get_trades",
               return_value=trades):
        row = logged_in.get("/api/v1/market/tape?symbols=NVDA").get_json()["rows"][0]
    assert row["context_kind"] == "position"
    assert row["context_label"] == "-0.5R"


def test_tape_plan_only_row_shows_pct_to_entry(logged_in):
    """A plan with no open position renders the "% to entry" label.

    Regression test: `_tape_context` used to read `plan.entry` -- a name
    `TradePlanV2` does not have (it's `entry_price`) -- so this always fell
    back to the generic "planned" label via the getattr default.
    """
    plan = SimpleNamespace(ticker="AMD", entry_price=200.0, horizon_key="3m")
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={"AMD": 190.0}), \
         patch("swingbot.core.planning.plan_store.PlanStore.open_plans",
               return_value=[plan]):
        row = logged_in.get("/api/v1/market/tape?symbols=AMD").get_json()["rows"][0]
    assert row["context_kind"] == "plan"
    assert row["sort_rank"] == 1
    assert "% to entry" in row["context_label"]
    assert row["context_label"] == "3m 5.3% to entry"


def test_tape_earnings_context_shown_alone(logged_in):
    """No open position, no open plan -- just an earnings date, on its own.

    Earnings TODAY is used rather than a fixed offset so this holds no
    matter what day the suite runs on: "today" is always inside its own
    Monday-Sunday week.
    """
    today_iso = dt.date.today().isoformat()
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={"NVDA": 182.0}), \
         patch("swingbot.admin.api_v1.watchlist._next_earnings",
               return_value={"NVDA": (today_iso, None)}):
        row = logged_in.get("/api/v1/market/tape?symbols=NVDA").get_json()["rows"][0]
    assert row["context_kind"] == "earnings"
    assert row["context_label"] == "earnings 0d"
    assert row["sort_rank"] == 2


def test_tape_no_context_when_nothing_applies(logged_in):
    """No position, no plan, no known earnings date -- the bare fall-through."""
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={"NVDA": 182.0}), \
         patch("swingbot.admin.api_v1.watchlist._next_earnings",
               return_value={}):
        row = logged_in.get("/api/v1/market/tape?symbols=NVDA").get_json()["rows"][0]
    assert row["context_kind"] is None
    assert row["context_label"] is None
    assert row["sort_rank"] == 2


def test_tape_unpriced_symbol_still_returns_a_row(logged_in):
    """A flagged name must never silently vanish from the tape."""
    with patch("swingbot.core.marketdata.data.get_current_price_batch",
               return_value={}):
        row = logged_in.get("/api/v1/market/tape?symbols=ZZZZ").get_json()["rows"][0]
    assert row["symbol"] == "ZZZZ"
    assert row["price"] is None
    assert row["change_pct"] is None


def test_tape_as_of_is_iso_utc(logged_in):
    resp = logged_in.get("/api/v1/market/tape?symbols=")
    assert resp.get_json()["as_of"].endswith("+00:00")


# --- _tape_context's Monday-Sunday earnings window, in isolation ----------
#
# Both tests fix `today` explicitly (rather than deriving it from the wall
# clock) so the exact divergence between a rolling "0 <= days <= 7" window
# and the real Monday-Sunday week boundary is reproduced deterministically,
# regardless of which day the suite happens to run on.

def test_earnings_within_the_current_week_shows_context():
    # Imported inside the test, not at module scope -- market.py pulls in
    # `.auth`, which pulls in `swingbot.admin.app`, which registers every
    # api_v1 module (including this one) -- importing it before the app
    # fixture has done that is the circular-import deadlock this repo's
    # views already dodge by importing lazily; see market.py's own docstring.
    from swingbot.admin.api_v1.market import _tape_context

    today = dt.date(2026, 9, 8)                    # a Tuesday
    earnings_date = dt.date(2026, 9, 9)             # this week's Wednesday
    kind, label, rank = _tape_context(
        "NVDA", 100.0, {}, {}, {"NVDA": earnings_date}, today=today)
    assert kind == "earnings"
    assert label == "earnings 1d"
    assert rank == 2


def test_earnings_6_days_out_landing_next_monday_is_excluded():
    """The exact case a rolling `0 <= days <= 7` window gets wrong: 6 days
    from a Tuesday lands on NEXT week's Monday, outside the current
    Monday(2026-09-07)-Sunday(2026-09-13) week -- so this must show no
    earnings context at all, even though the old day-count window would
    have wrongly included it.
    """
    from swingbot.admin.api_v1.market import _tape_context

    today = dt.date(2026, 9, 8)                     # a Tuesday
    earnings_date = dt.date(2026, 9, 14)             # next week's Monday
    kind, label, rank = _tape_context(
        "NVDA", 100.0, {}, {}, {"NVDA": earnings_date}, today=today)
    assert kind is None
    assert label is None
    assert rank == 2
