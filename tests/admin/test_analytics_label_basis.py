"""v189 D6: the win-rate label basis is visible. Scaled-out closes are
labelled by net R from LABEL_BASIS_SINCE (D2, not backfilled), so the
Analytics performance payload carries the date and the scratch/unscored
counts the win rate leaves out -- the step at deploy reads as a change of
basis, not an improvement. Every expected value is hand-computed."""
import pytest

from swingbot.core.analytics import metrics
from tests.admin.api_v1_contract import NULLABLE_STR, assert_shape
from tests.admin.test_api_v1_trades import _trade
from tests.analytics.test_golden_partial_trade_metrics import golden_closed_trade
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}


def _row(trade_id: str, status: str, close_reason=None, **over) -> dict:
    t = _trade(trade_id, plan_id=None, status=status)
    t["close_reason"] = close_reason
    t["horizon_key"] = "4w"
    t.update(over)
    return t


# -- metrics.label_counts ----------------------------------------------------

def test_an_empty_book_counts_zero_of_each():
    assert metrics.label_counts([]) == {"scratch": 0, "unscored": 0}


def test_counts_closed_rows_by_exact_close_reason():
    closed = [
        {"status": "closed", "close_reason": "scratch"},
        {"status": "closed", "close_reason": "scratch"},
        {"status": "closed", "close_reason": "unscored"},
        {"status": "closed", "close_reason": "manual"},
        {"status": "closed", "close_reason": None},
        {"status": "closed"},
    ]
    assert metrics.label_counts(closed) == {"scratch": 2, "unscored": 1}


def test_a_win_loss_or_open_row_never_counts_whatever_its_close_reason():
    closed = [{"status": "win", "close_reason": "scratch"},
              {"status": "loss", "close_reason": "unscored"},
              {"status": "open", "close_reason": "scratch"}]
    assert metrics.label_counts(closed) == {"scratch": 0, "unscored": 0}


def test_near_misses_of_the_vocabulary_do_not_count():
    closed = [{"status": "closed", "close_reason": "Scratch"},
              {"status": "closed", "close_reason": "scratch "},
              {"status": "closed", "close_reason": "timeout"}]
    assert metrics.label_counts(closed) == {"scratch": 0, "unscored": 0}


def test_the_golden_trade_closed_at_net_zero_is_one_scratch():
    """Runner out at 90: 0.5 x +2R + 0.5 x -2R = 0.00R, inside the band.
    The label `net_outcome` gives it is the one `label_counts` counts."""
    trade = golden_closed_trade({"runner_exit": 90.0, "status": "closed",
                                 "close_reason": "scratch"})
    assert metrics.net_outcome(trade) == ("closed", "scratch")
    assert metrics.label_counts([trade]) == {"scratch": 1, "unscored": 0}


# -- /api/v1/analytics/performance -------------------------------------------

@pytest.fixture
def seed(admin_app, tmp_path):
    def _seed(trades=()):
        seed_store("trades", list(trades))
    return _seed


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


def _perf(client, query=""):
    return client.get("/api/v1/analytics/performance" + query).get_json()


def test_the_payload_declares_the_label_basis_keys(seed, logged_in):
    seed()
    body = _perf(logged_in)
    assert_shape({k: body[k] for k in ("scratch_n", "unscored_n", "label_basis_since")},
                 {"scratch_n": int, "unscored_n": int, "label_basis_since": NULLABLE_STR},
                 where="performance")
    assert body["scratch_n"] == 0 and body["unscored_n"] == 0


def test_counts_sit_beside_a_win_rate_that_leaves_them_out(seed, logged_in):
    """2 wins, 1 loss, 2 scratches, 1 unscored, 1 manual close: the rate is
    2 / 3 over win_rate_n 3; the four `closed` rows are reported, not rated."""
    seed(trades=[
        _row("a" * 16, "win"), _row("b" * 16, "win"), _row("c" * 16, "loss"),
        _row("d" * 16, "closed", "scratch"), _row("e" * 16, "closed", "scratch"),
        _row("f" * 16, "closed", "unscored"), _row("g" * 16, "closed", "manual"),
    ])
    body = _perf(logged_in)
    assert body["win_rate_n"] == 3
    assert body["win_rate"] == pytest.approx(200 / 3)
    assert body["scratch_n"] == 2 and body["unscored_n"] == 1


def test_counts_follow_the_scope(seed, logged_in):
    """`_trade` closes on 2026-08-04; `?from=2026-08-01&horizon=4w` keeps
    only the first row (the second is 2w, the third closed in July)."""
    seed(trades=[
        _row("a" * 16, "closed", "scratch"),
        _row("b" * 16, "closed", "scratch", horizon_key="2w"),
        _row("c" * 16, "closed", "unscored", closed_at="2026-07-10T15:00:00+00:00"),
    ])
    unscoped = _perf(logged_in)
    assert unscoped["scratch_n"] == 2 and unscoped["unscored_n"] == 1
    scoped = _perf(logged_in, "?from=2026-08-01&horizon=4w")
    assert scoped["scratch_n"] == 1 and scoped["unscored_n"] == 0


def test_open_trades_are_not_counted(seed, logged_in):
    seed(trades=[_row("a" * 16, "open", "scratch")])
    body = _perf(logged_in)
    assert body["scratch_n"] == 0 and body["unscored_n"] == 0


def test_label_basis_since_is_the_metrics_constant(seed, logged_in):
    """None before the release task, the merge date after it -- either way
    the payload carries the constant itself, never a copy."""
    seed()
    assert _perf(logged_in)["label_basis_since"] == metrics.LABEL_BASIS_SINCE


def test_label_basis_since_echoes_the_constant_at_request_time(seed, logged_in, monkeypatch):
    seed()
    monkeypatch.setattr(metrics, "LABEL_BASIS_SINCE", "2026-10-24")
    assert _perf(logged_in)["label_basis_since"] == "2026-10-24"
