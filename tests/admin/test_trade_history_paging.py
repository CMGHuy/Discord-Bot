"""Trade History scoping/filtering/paging (plan v9, H1).

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


def test_endpoint_requires_auth(client, seeded):
    r = client.get("/api/trade-history")
    assert r.status_code == 401
    assert r.get_json()["error"] == "auth"


def test_endpoint_all_mode_totals_and_pages(client, auth, seeded):
    d = _get(client, auth, mode="all", page=1, per_page=25)
    assert d["total"] == 62
    assert d["pages"] == 3
    assert d["shown"] == 25
    assert d["rows_html"].count("<tr") >= 25


def test_endpoint_today_mode_scopes_to_today(client, auth, seeded):
    d = _get(client, auth, mode="today", per_page=25)
    assert d["total"] == 2
    assert "NVDA" in d["rows_html"]


def test_endpoint_active_matches_today(client, auth, seeded):
    assert (_get(client, auth, mode="active")["total"]
            == _get(client, auth, mode="today")["total"] == 2)


def test_endpoint_filter_reaches_beyond_the_first_page(client, auth, seeded):
    """NVDA trades sort newest-first so they are on page 1 here; the point is
    that filtering narrows the TOTAL, i.e. it ran server-side over everything
    rather than over one page's DOM."""
    d = _get(client, auth, mode="all", ticker="NVDA", per_page=25)
    assert d["total"] == 2 and d["pages"] == 1


def test_endpoint_pages_are_disjoint(client, auth, seeded):
    import re
    seen = []
    for page in (1, 2, 3):
        html = _get(client, auth, mode="all", page=page, per_page=25)["rows_html"]
        seen += re.findall(r'id="ct-row-([^"]+)"', html)
    assert len(seen) == len(set(seen)) == 62


def test_endpoint_row_numbers_continue_across_pages(client, auth, seeded):
    p2 = _get(client, auth, mode="all", page=2, per_page=25)["rows_html"]
    assert '<span class="row-num">26</span>' in p2


def test_endpoint_rejects_junk_params_without_500(client, auth, seeded):
    for params in ({"page": "abc"}, {"per_page": "9999"}, {"page": "-5"},
                   {"mode": "bogus"}, {"per_page": "0.5"}):
        r = client.get("/api/trade-history", query_string=params, headers=auth)
        assert r.status_code == 200, (params, r.status_code)


def test_endpoint_per_page_clamped_to_allowed_set(client, auth, seeded):
    # 9999 is not offered by the selector; must fall back to 25, not honour it
    assert _get(client, auth, mode="all", per_page=9999)["shown"] == 25


def test_endpoint_out_of_range_page_is_empty_not_an_error(client, auth, seeded):
    d = _get(client, auth, mode="all", page=99, per_page=25)
    assert d["shown"] == 0 and d["total"] == 62


# ── Dashboard page integration (H5/H6) ──────────────────────────────────────

def _row_ids(html):
    import re
    m = re.search(r'id="closed-trades-table".*?<tbody>(.*?)</tbody>', html, re.S)
    return re.findall(r'id="ct-row-([^"]+)"', m.group(1)) if m else []


def test_dashboard_today_mode_renders_only_todays_history(client, auth, seeded):
    html = client.get("/?mode=today", headers=auth).get_data(as_text=True)
    ids = _row_ids(html)
    assert set(ids) == {"today1", "today2"}, ids


def test_dashboard_active_mode_renders_only_todays_history(client, auth, seeded):
    assert set(_row_ids(client.get("/?mode=active", headers=auth).get_data(as_text=True))) \
        == {"today1", "today2"}


def test_dashboard_all_mode_renders_first_page_only(client, auth, seeded):
    ids = _row_ids(client.get("/?mode=all", headers=auth).get_data(as_text=True))
    assert len(ids) == 25, len(ids)          # first page, not all 62
    assert "today1" in ids                    # newest-closed first


def test_dashboard_no_longer_advertises_a_truncated_history(client, auth, seeded):
    html = client.get("/?mode=all", headers=auth).get_data(as_text=True)
    assert "Showing latest" not in html


def test_filter_dropdown_options_still_come_from_full_history(client, auth, seeded):
    """Regression guard: options must reflect every ticker in the log, not
    just the ones on the current page. AAPL only exists in older trades."""
    html = client.get("/?mode=today", headers=auth).get_data(as_text=True)
    import re
    sel = re.search(r'id="ct-filter-ticker".*?</select>', html, re.S).group(0)
    assert "AAPL" in sel and "NVDA" in sel


def test_endpoint_sorting_is_server_side(client, auth, seeded):
    asc = _get(client, auth, mode="all", sort_by="closed", sort_dir="asc", per_page=10)
    desc = _get(client, auth, mode="all", sort_by="closed", sort_dir="desc", per_page=10)
    import re
    a = re.findall(r'id="ct-row-([^"]+)"', asc["rows_html"])
    d = re.findall(r'id="ct-row-([^"]+)"', desc["rows_html"])
    assert a and d and a[0] != d[0]
    assert a[0] == "old59"      # oldest close
    assert d[0] in ("today1", "today2")


def test_endpoint_unknown_sort_column_falls_back(client, auth, seeded):
    d = _get(client, auth, mode="all", sort_by="not_a_column", per_page=10)
    assert d["total"] == 62
