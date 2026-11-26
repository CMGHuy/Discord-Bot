"""v248 V248-2: the status-bar arithmetic lives in trade_progress.py; the
client's ui/position-progress.ts (V248-10) is held to it by the same fixture."""
import copy
import json
from pathlib import Path

import pytest

import swingbot.admin.app  # noqa: F401  (app first: api_v1 modules import under it)
from swingbot.admin.api_v1 import trade_progress as tp
from swingbot.admin.api_v1 import trades

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "v248" / "progress_cases.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))
BAR_KEYS = ("progress_pct", "entry_pct", "progress_band", "blink_seconds", "status_label")


def _shown_r(row, price):
    """The R `_attach_unrealized_pnl` puts on the row at `price`."""
    if price is None or row.get("entry") is None:
        return None
    if row["status"] in tp.TERMINAL_STATUSES or row["status"] == "PENDING":
        return None
    return trades._live_r(row, price)


def test_fixture_is_well_formed():
    names = [c["name"] for c in CASES]
    assert len(names) == 16 and len(set(names)) == 16
    for case in CASES:
        assert set(case) == {"name", "row", "price", "price_kind", "expected"}
        assert set(case["expected"]) == {*BAR_KEYS, "r_multiple"}
        assert case["price_kind"] in (tp.PRICE_LIVE, tp.PRICE_PREV_CLOSE)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_server_matches_the_shared_fixture(case):
    row = copy.deepcopy(case["row"])
    got = tp.row_progress(row, case["price"], price_kind=case["price_kind"])
    assert set(got) == set(BAR_KEYS)
    assert got == {k: case["expected"][k] for k in BAR_KEYS}
    assert _shown_r(row, case["price"]) == case["expected"]["r_multiple"]
    assert row == case["row"]                               # pure: the row is not touched


def test_terminal_set_is_the_trades_one():
    assert tp.TERMINAL_STATUSES == frozenset(trades._TERMINAL)


@pytest.mark.parametrize("price", [80.0, 92.0, 105.0, 119.0, 140.0])
def test_prev_close_never_claims_a_stop_or_target(price):
    row = next(c["row"] for c in CASES if c["name"] == "bull_live_toward_target")
    got = tp.row_progress(row, price, price_kind=tp.PRICE_PREV_CLOSE)
    live = tp.row_progress(row, price)
    assert got["progress_band"] == "neutral" and got["blink_seconds"] is None
    assert got["status_label"] == tp.PREV_CLOSE_LABEL
    assert (got["progress_pct"], got["entry_pct"]) == (live["progress_pct"], live["entry_pct"])


def test_trades_wrappers_delegate():
    bull = next(c["row"] for c in CASES if c["name"] == "bull_live_near_stop")
    trail = next(c["row"] for c in CASES if c["name"] == "trailing_short_live")
    assert trades._status_fields(bull, 92.0) == tp.status_fields(bull, 92.0)
    wrapped = trades._trailing_status_fields(trail, 50.0)
    assert {k: wrapped[k] for k in BAR_KEYS} == tp.trailing_bar_fields(trail, 50.0)
    assert {"stop_pnl_pct", "best_pnl_pct"} <= set(wrapped)        # runner P&L still merged
    chip = trades._trailing_status_fields({**trail, "runner_best": None}, 50.0)
    assert "stop_pnl_pct" not in chip                               # the chip path adds nothing


def test_attach_status_fields_uses_row_progress_for_every_kind():
    rows = [copy.deepcopy(c["row"]) | {"current_price": c["price"]}
            for c in CASES if c["price_kind"] == tp.PRICE_LIVE]
    trades._attach_status_fields(rows)
    for row in rows:
        assert {k: row[k] for k in BAR_KEYS} == tp.row_progress(row, row["current_price"])
