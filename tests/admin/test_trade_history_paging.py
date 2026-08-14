"""Trade History scoping/filtering/paging (plan v9, H1).

NG19 TRIAGE — **query-level · KEEP UNCHANGED.** Spec v15 Decision 4 names
this file explicitly. It targets `query_closed_trades()`, which
/api/v1/trades reuses -- the filter-then-sort-then-slice ordering these pin
is the same ordering that makes the v1 collection's `total` a post-filter
pre-slice count. Deleting these would remove the only coverage of that.


The table used to ignore the dashboard's Today+Open / Today only / All days
toggle entirely. These lock in the three behaviours that replaced that:

  * "today" and "active" narrow to trades CLOSED today, and are identical to
    each other here (open trades never reach this table, and that is the only
    thing separating those two modes).
  * filters apply to the WHOLE scoped set, not just the visible page -- the
    failure mode that makes server-side paging with client-side filtering
    wrong.
  * pages are disjoint and their union is the full filtered set.
"""
from datetime import datetime, timedelta, timezone

import pytest

from swingbot.admin.dashboard import _BERLIN_TZ
from swingbot.admin.dashboard import query_closed_trades as _query_closed_trades


def _trade(tid, *, status="win", closed=None, ticker="AAPL",
           horizon="2w", direction="bullish", conf=3):
    return {
        "id": tid, "status": status, "ticker": ticker,
        "closed_at": closed, "opened_at": closed,
        "horizon_key": horizon, "direction": direction,
        "confidence_level": conf, "strategies": ["RSI"],
    }


def _iso(days_ago=0, hour=12):
    """A timestamp `days_ago` before today, anchored on the SAME calendar day
    the code under test uses.

    This built its stamps from UTC's date originally, while `is_today_berlin`
    compares against `datetime.now(Europe/Berlin).date()`. Those two dates
    disagree for the ~2h window each evening when Berlin has rolled over but
    UTC has not (22:00-24:00 UTC under CEST) -- so "today" in the fixture was
    yesterday-in-Berlin, and every today-mode test failed, deterministically,
    for two hours a day and passed the other twenty-two.

    Anchoring on _BERLIN_TZ (the module's own constant, with its UTC fallback
    when zoneinfo is unavailable) makes the fixture agree with the code by
    construction instead of by coincidence.
    """
    tz = _BERLIN_TZ or timezone.utc
    d = datetime.now(tz).replace(hour=hour, minute=0, second=0, microsecond=0)
    return (d - timedelta(days=days_ago)).isoformat()


@pytest.fixture
def trades():
    return [
        _trade("t-today-1", closed=_iso(0, 9)),
        _trade("t-today-2", closed=_iso(0, 14), status="loss", ticker="MSFT"),
        _trade("t-old-1", closed=_iso(3)),
        _trade("t-old-2", closed=_iso(10), ticker="MSFT"),
        _trade("t-open", status="open", closed=None),
    ]


def test_open_trades_never_appear(trades):
    for mode in ("all", "today", "active"):
        rows, _ = _query_closed_trades(trades, mode=mode, per_page=0)
        assert all(r["status"] != "open" for r in rows), mode


def test_all_mode_returns_every_closed_trade(trades):
    rows, total = _query_closed_trades(trades, mode="all", per_page=0)
    assert total == 4
    assert {r["id"] for r in rows} == {"t-today-1", "t-today-2", "t-old-1", "t-old-2"}


def test_today_mode_keeps_only_trades_closed_today(trades):
    rows, total = _query_closed_trades(trades, mode="today", per_page=0)
    assert total == 2
    assert {r["id"] for r in rows} == {"t-today-1", "t-today-2"}


def test_active_mode_is_identical_to_today_for_this_table(trades):
    today, _ = _query_closed_trades(trades, mode="today", per_page=0)
    active, _ = _query_closed_trades(trades, mode="active", per_page=0)
    assert [r["id"] for r in today] == [r["id"] for r in active]


def test_sorted_by_closed_at_descending(trades):
    rows, _ = _query_closed_trades(trades, mode="all", per_page=0)
    stamps = [r["closed_at"] for r in rows]
    assert stamps == sorted(stamps, reverse=True)


@pytest.mark.parametrize("key,value,expected", [
    ("ticker", "MSFT", {"t-today-2", "t-old-2"}),
    ("outcome", "loss", {"t-today-2"}),
    ("horizon", "2w", {"t-today-1", "t-today-2", "t-old-1", "t-old-2"}),
    ("dir", "bullish", {"t-today-1", "t-today-2", "t-old-1", "t-old-2"}),
])
def test_each_filter_applies(trades, key, value, expected):
    rows, total = _query_closed_trades(trades, mode="all", filters={key: value}, per_page=0)
    assert {r["id"] for r in rows} == expected
    assert total == len(expected)


def test_blank_filter_value_means_no_filter(trades):
    rows, total = _query_closed_trades(trades, mode="all", filters={"ticker": ""}, per_page=0)
    assert total == 4


def test_filters_combine(trades):
    rows, total = _query_closed_trades(
        trades, mode="all", filters={"ticker": "MSFT", "outcome": "loss"}, per_page=0)
    assert {r["id"] for r in rows} == {"t-today-2"}
    assert total == 1


def test_filter_applies_across_all_pages_not_just_the_first():
    """The whole point of moving filters server-side: a match on page 3 must
    still be found when the filter is applied, even though it is nowhere near
    the first page of the unfiltered set."""
    many = [_trade(f"t{i}", closed=_iso(i)) for i in range(60)]
    many.append(_trade("needle", closed=_iso(90), ticker="NVDA"))
    rows, total = _query_closed_trades(many, mode="all", filters={"ticker": "NVDA"}, per_page=25)
    assert total == 1
    assert [r["id"] for r in rows] == ["needle"]


def test_pages_are_disjoint_and_cover_the_whole_set():
    many = [_trade(f"t{i}", closed=_iso(i)) for i in range(60)]
    seen, page = [], 1
    while True:
        rows, total = _query_closed_trades(many, mode="all", page=page, per_page=25)
        if not rows:
            break
        seen += [r["id"] for r in rows]
        page += 1
    assert total == 60
    assert len(seen) == len(set(seen)) == 60


def test_page_one_is_not_empty_when_trades_exist(trades):
    """Regression guard for 32afe78 -- Trade History showed no trades on page 1."""
    rows, total = _query_closed_trades(trades, mode="all", page=1, per_page=25)
    assert total == 4 and rows


def test_out_of_range_page_is_empty_but_total_is_honest(trades):
    rows, total = _query_closed_trades(trades, mode="all", page=99, per_page=25)
    assert rows == []
    assert total == 4


def test_per_page_zero_means_all(trades):
    rows, total = _query_closed_trades(trades, mode="all", page=3, per_page=0)
    assert len(rows) == total == 4


# ── /api/trade-history endpoint (H2) ────────────────────────────────────────

def _seed(tmp_path, trades):
    import json as _json
    (tmp_path / "trades.json").write_text(_json.dumps(trades), encoding="utf-8")


@pytest.fixture
def seeded(tmp_path, admin_app):
    """60 old + 2 closed-today trades, written straight to the isolated
    trades.json the admin_app fixture already points DATA_DIR at."""
    rows = [_trade(f"old{i}", closed=_iso(i + 1), ticker="AAPL") for i in range(60)]
    rows += [_trade("today1", closed=_iso(0, 9), ticker="NVDA"),
             _trade("today2", closed=_iso(0, 14), ticker="NVDA", status="loss")]
    for r in rows:
        r.update(entry=100.0, exit_price=105.0, stop_loss=95.0)
    _seed(tmp_path, rows)
    return rows


def _get(client, auth, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/api/trade-history?{qs}", headers=auth)
    assert r.status_code == 200, r.status_code
    return r.get_json()


# ── Dashboard page integration (H5/H6) ──────────────────────────────────────

def _row_ids(html):
    import re
    m = re.search(r'id="closed-trades-table".*?<tbody>(.*?)</tbody>', html, re.S)
    return re.findall(r'id="ct-row-([^"]+)"', m.group(1)) if m else []


def test_dashboard_no_longer_advertises_a_truncated_history(client, auth, seeded):
    html = client.get("/jinja/dashboard?mode=all", headers=auth).get_data(as_text=True)
    assert "Showing latest" not in html


