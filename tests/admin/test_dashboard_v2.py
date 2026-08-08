"""Dashboard v2 behaviours: bounded history, pedigree chips, leg rows,
lifecycle strip, equity sparkline.

Two response bodies are exercised here and the distinction matters:

  * "/dashboard/fragment" -- the polled fragment: session banner, lifecycle
    strip, stat cards, Open Trades. Re-rendered every few seconds.
  * "/" -- the full page, which contains that fragment inline PLUS the Trade
    History card. History markup is static shell content filled by
    /api/trade-history, so it is deliberately absent from the fragment.
"""
import json
import os


def _seed_many_closed_trades(data_dir, n):
    trades = []
    for i in range(n):
        trades.append({
            "id": f"t{i}", "ticker": "AAA", "status": "win", "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "exit_price": 110.0,
            "opened_at": "2026-01-01T00:00:00+00:00",
            "closed_at": f"2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}T00:00:00+00:00",
            "confidence_level": 3, "confidence_score": 60, "strategy": "RSI", "horizon_key": "4w",
        })
    with open(os.path.join(data_dir, "trades.json"), "w") as f:
        json.dump(trades, f)


def test_dashboard_renders_only_the_first_page_of_history(client, auth, admin_app):
    """Was: bounded at 500 rows with a 'Showing latest 500 of 510' banner.

    Plan v9 replaced that cap with real server-side paging -- the page renders
    only the first page and the rest is fetched from /api/trade-history, so
    the payload is far smaller AND the older trades the banner used to
    apologise for are now actually reachable.
    """
    from swingbot import config
    _seed_many_closed_trades(config.DATA_DIR, 510)
    r = client.get("/?mode=all", headers=auth)
    html = r.data.decode("utf-8")
    assert html.count('id="ct-row-') == 25
    assert 'id="ct-total-count">510<' in html     # full total still reported


def test_history_is_not_part_of_the_polled_fragment(client, auth, admin_app):
    """Trade History belongs to the page shell, not the 5s poll.

    It is owned by /api/trade-history from first paint onward, so re-rendering
    its rows and its six filter dropdowns on every tick only ever produced
    markup the browser immediately replaced.
    """
    from swingbot import config
    _seed_many_closed_trades(config.DATA_DIR, 30)
    fragment = client.get("/dashboard/fragment?mode=all", headers=auth).data.decode("utf-8")
    assert "ct-row-" not in fragment
    assert "closed-trades-table" not in fragment
    assert "ct-filter-ticker" not in fragment

    page = client.get("/?mode=all", headers=auth).data.decode("utf-8")
    assert "closed-trades-table" in page


def test_fragment_carries_no_script_tags(client, auth, admin_app):
    """The fragment is morphdom-patched into the page, and a <script> that
    arrives by DOM patching never executes. Behaviour lives in
    static/dashboard.js precisely so nothing here depends on that."""
    from swingbot import config
    _seed_many_closed_trades(config.DATA_DIR, 5)
    fragment = client.get("/dashboard/fragment?mode=all", headers=auth).data.decode("utf-8")
    assert "<script" not in fragment.lower()


def test_dashboard_never_advertises_truncated_history(client, auth, admin_app):
    """The truncation banner is gone for good -- with paging there is no
    longer any history the table cannot reach."""
    from swingbot import config
    _seed_many_closed_trades(config.DATA_DIR, 510)
    r = client.get("/?mode=all", headers=auth)
    assert "Showing latest" not in r.data.decode("utf-8")


def test_dashboard_open_trade_renders_pedigree_chip_and_runner_row(client, auth, admin_app):
    from swingbot import config
    trades = [{
        "id": "t1", "ticker": "AAPL", "status": "open", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
        "opened_at": "2026-07-01T00:00:00+00:00",
        "confidence_level": 3, "confidence_score": 60, "strategy": "RSI", "horizon_key": "4w",
        "tier": "A", "badge": "VALIDATED",
        "legs": [{"fraction": 0.5, "exit_price": 104.0, "r": 0.4},
                {"fraction": 0.5, "exit_price": None, "r": None}],
    }]
    with open(os.path.join(config.DATA_DIR, "trades.json"), "w") as f:
        json.dump(trades, f)
    r = client.get("/dashboard/fragment", headers=auth)
    html = r.data.decode("utf-8")
    assert "chip-tier-a" in html
    assert "runner" in html


def test_dashboard_fragment_shows_lifecycle_strip_and_equity_sparkline(client, auth, admin_app, monkeypatch):
    fake_snapshot = {
        "built_at": "x",
        "equity_curve": {
            "points": [{"date": f"2026-06-{i + 1:02d}", "balance": 10000 + i * 10, "pnl": 10.0} for i in range(30)],
            "skipped_n": 0,
        },
    }
    monkeypatch.setattr("swingbot.admin.dashboard.load_snapshot", lambda max_age_seconds=3600: fake_snapshot)
    monkeypatch.setattr("swingbot.admin.pages.rank_plans", lambda plans: [])
    r = client.get("/dashboard/fragment", headers=auth)
    html = r.data.decode("utf-8")
    assert "lifecycle-strip" in html
    assert "<svg" in html


def _closed_tbody(html):
    """The <tbody> of the Trade History table -- the exact node the client-side
    paginator scans with `#closed-trades-table tbody tr`."""
    table = html.split('id="closed-trades-table"', 1)[1]
    return table.split("<tbody>", 1)[1].split("</tbody>", 1)[0]


def _seed_closed_pair_with_runner(data_dir):
    """Two closed trades, the NEWER one scaled out (2 legs). The scale-out
    trade emits a second <tr> for its runner detail line -- that extra row is
    what the paginator must not mistake for a trade."""
    base = {
        "status": "win", "direction": "bullish", "entry": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0, "exit_price": 110.0,
        "opened_at": "2026-07-01T00:00:00+00:00", "confidence_level": 3,
        "confidence_score": 60, "strategy": "RSI", "horizon_key": "4w",
    }
    trades = [
        dict(base, id="t0", ticker="AAA", closed_at="2026-07-20T00:00:00+00:00",
             legs=[{"fraction": 0.5, "exit_price": 104.0, "r": 0.4},
                   {"fraction": 0.5, "exit_price": 110.0, "r": 2.0}]),
        dict(base, id="t1", ticker="BBB", closed_at="2026-07-19T00:00:00+00:00"),
    ]
    with open(os.path.join(data_dir, "trades.json"), "w") as f:
        json.dump(trades, f)


def test_closed_runner_row_is_marked_so_pagination_can_skip_it(client, auth, admin_app):
    """A scale-out trade's runner row sits in the same <tbody> as real trade
    rows but carries no .row-num -- the paginator used to count it as a trade
    and then throw on `.row-num.textContent`, aborting render() mid-page. It
    must be identifiable as a non-trade row and tied to its parent trade."""
    from swingbot import config
    _seed_closed_pair_with_runner(config.DATA_DIR)
    html = client.get("/?mode=all", headers=auth).data.decode("utf-8")
    tbody = _closed_tbody(html)

    leg_rows = [row for row in tbody.split("<tr")[1:] if "ct-leg-row" in row.split(">", 1)[0]]
    assert len(leg_rows) == 1, "the runner detail row must be marked ct-leg-row"
    assert 'data-leg-for="t0"' in leg_rows[0], "and tied to the trade it belongs to"


def test_every_paginated_closed_row_has_a_row_number(client, auth, admin_app):
    """render() writes `.row-num` on every row it shows. Any row the paginator
    counts but that has no .row-num crashes it, so the two sets must match:
    2 trades -> 2 .row-num spans, and exactly 1 extra (excluded) leg row."""
    from swingbot import config
    _seed_closed_pair_with_runner(config.DATA_DIR)
    html = client.get("/?mode=all", headers=auth).data.decode("utf-8")
    tbody = _closed_tbody(html)

    total_rows = tbody.count("<tr")
    paginated = [row for row in tbody.split("<tr")[1:] if "ct-leg-row" not in row.split(">", 1)[0]]
    assert len(paginated) == 2, "one paginatable row per closed trade"
    assert total_rows == 3, "2 trade rows + 1 runner row"
    for row in paginated:
        assert 'class="row-num"' in row


def test_open_runner_row_is_marked_so_pagination_can_skip_it(client, auth, admin_app):
    """The Open Trades table renders the same runner continuation row and
    paginates the same way, so it needs the same exclusion marker."""
    from swingbot import config
    trades = [{
        "id": "t1", "ticker": "AAPL", "status": "open", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
        "opened_at": "2026-07-01T00:00:00+00:00", "confidence_level": 3,
        "confidence_score": 60, "strategy": "RSI", "horizon_key": "4w",
        "legs": [{"fraction": 0.5, "exit_price": 104.0, "r": 0.4},
                 {"fraction": 0.5, "exit_price": None, "r": None}],
    }]
    with open(os.path.join(config.DATA_DIR, "trades.json"), "w") as f:
        json.dump(trades, f)
    html = client.get("/dashboard/fragment", headers=auth).data.decode("utf-8")
    tbody = html.split('id="trades-table"', 1)[1].split("<tbody>", 1)[1].split("</tbody>", 1)[0]

    rows = tbody.split("<tr")[1:]
    leg_rows = [r for r in rows if "ot-leg-row" in r.split(">", 1)[0]]
    trade_rows = [r for r in rows if "ot-leg-row" not in r.split(">", 1)[0]]
    assert len(leg_rows) == 1 and 'data-leg-for="t1"' in leg_rows[0]
    assert len(trade_rows) == 1 and 'data-trade-id="t1"' in trade_rows[0]


def test_history_defaults_to_compact_density(client, auth, admin_app):
    """A browser with no stored preference must get the compact table."""
    from swingbot import config
    _seed_closed_pair_with_runner(config.DATA_DIR)
    html = client.get("/?mode=all", headers=auth).data.decode("utf-8")
    assert 'data-density-for="ct"' in html
    wrapper = html.split('data-density-for="ct"', 1)[0].rsplit("<div", 1)[1]
    assert "density-compact" in wrapper


def test_history_full_only_columns_are_marked(client, auth, admin_app):
    """The 8 analytical columns must carry col-full on BOTH th and td, or
    they will not hide together."""
    from swingbot import config
    _seed_closed_pair_with_runner(config.DATA_DIR)
    html = client.get("/?mode=all", headers=auth).data.decode("utf-8")
    table = html.split('id="closed-trades-table"', 1)[1].split("</table>", 1)[0]
    head, body = table.split("<tbody>", 1)
    for col in ("strategy", "horizon", "dir", "conf", "entry", "exit", "pnlpct", "opened"):
        th = [h for h in head.split("<th")[1:] if 'data-col-id="%s"' % col in h]
        assert th and "col-full" in th[0].split(">", 1)[0], "th %s missing col-full" % col
    # one col-full td per full-only column, per trade row (2 trades seeded)
    assert body.count("col-full") == 8 * 2


def test_history_still_renders_every_column_server_side(client, auth, admin_app):
    """Density is presentational -- nothing may be dropped server-side."""
    import re
    from swingbot import config
    _seed_closed_pair_with_runner(config.DATA_DIR)
    html = client.get("/?mode=all", headers=auth).data.decode("utf-8")
    table = html.split('id="closed-trades-table"', 1)[1].split("</table>", 1)[0]
    # NB: count "<th " / "<th>" -- a bare "<th" also matches "<thead>".
    assert len(re.findall(r"<th[ >]", table)) == 16, "all 16 columns must still render"


def _seed_open_trade_with_runner(data_dir):
    trades = [{
        "id": "o1", "ticker": "AAPL", "status": "open", "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
        "opened_at": "2026-07-01T00:00:00+00:00", "confidence_level": 3,
        "confidence_score": 60, "strategy": "RSI", "horizon_key": "4w",
        "legs": [{"fraction": 0.5, "exit_price": 104.0, "r": 0.4},
                 {"fraction": 0.5, "exit_price": None, "r": None}],
    }]
    with open(os.path.join(data_dir, "trades.json"), "w") as f:
        json.dump(trades, f)


def test_open_trades_cell_count_matches_header(client, auth, admin_app):
    """reorderTableColumns() bails out unless every trade row has exactly as
    many cells as the header has columns -- adding Plan must not break it."""
    import re
    from swingbot import config
    _seed_open_trade_with_runner(config.DATA_DIR)
    html = client.get("/dashboard/fragment", headers=auth).data.decode("utf-8")
    table = html.split('id="trades-table"', 1)[1].split("</table>", 1)[0]
    head, body = table.split("<tbody>", 1)
    # NB: count "<th " / "<th>" -- a bare "<th" also matches "<thead>".
    n_cols = len(re.findall(r"<th[ >]", head))
    assert n_cols == 19, "18 original columns + Plan"
    trade_row = [r for r in body.split("<tr")[1:] if "ot-leg-row" not in r.split(">", 1)[0]][0]
    assert trade_row.count("<td") == n_cols


def test_open_trades_leg_row_colspan_covers_every_column(client, auth, admin_app):
    from swingbot import config
    _seed_open_trade_with_runner(config.DATA_DIR)
    html = client.get("/dashboard/fragment", headers=auth).data.decode("utf-8")
    table = html.split('id="trades-table"', 1)[1].split("</table>", 1)[0]
    leg = [r for r in table.split("<tr")[1:] if "ot-leg-row" in r.split(">", 1)[0]][0]
    assert 'colspan="17"' in leg, "2 empty td + colspan 17 == 19 columns"


def test_open_trades_defaults_to_compact_density(client, auth, admin_app):
    from swingbot import config
    _seed_open_trade_with_runner(config.DATA_DIR)
    html = client.get("/dashboard/fragment", headers=auth).data.decode("utf-8")
    assert 'data-density-for="ot"' in html
    wrapper = html.split('data-density-for="ot"', 1)[0].rsplit("<div", 1)[1]
    assert "density-compact" in wrapper


def test_open_trades_full_only_columns_are_marked(client, auth, admin_app):
    from swingbot import config
    _seed_open_trade_with_runner(config.DATA_DIR)
    html = client.get("/dashboard/fragment", headers=auth).data.decode("utf-8")
    table = html.split('id="trades-table"', 1)[1].split("</table>", 1)[0]
    head, body = table.split("<tbody>", 1)
    for col in ("strategy", "horizon", "direction", "confidence", "score",
                "entry", "stop", "target", "rr", "size", "opened"):
        th = [h for h in head.split("<th")[1:] if 'data-col-id="%s"' % col in h]
        assert th and "col-full" in th[0].split(">", 1)[0], "th %s missing col-full" % col


def _seed_trades(data_dir, trades):
    with open(os.path.join(data_dir, "trades.json"), "w") as f:
        json.dump(trades, f)


def _badged_trade(tid, status, badge, **extra):
    t = {
        "id": tid, "ticker": "AAPL", "status": status, "direction": "bullish",
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
        "opened_at": "2026-07-01T00:00:00+00:00",
        "confidence_level": 3, "confidence_score": 60, "strategy": "RSI",
        "horizon_key": "4w", "tier": "A", "badge": badge,
    }
    t.update(extra)
    return t


# The VALIDATED/WEAK badge is per-trade detail, not a column to scan a list by:
# it belongs on the trade's own page and nowhere in the two dashboard tables.
# The tier chip is a separate decision and deliberately stays in both, so each
# test pins that too -- otherwise "badge is gone" would also pass if a careless
# edit stripped the whole pedigree block.

def test_open_trades_table_does_not_show_the_validation_badge(client, auth, admin_app):
    from swingbot import config
    _seed_trades(config.DATA_DIR, [_badged_trade("t1", "open", "VALIDATED")])
    html = client.get("/dashboard/fragment", headers=auth).data.decode("utf-8")
    assert "VALIDATED" not in html
    assert "chip-tier-a" in html


def test_closed_trades_table_does_not_show_the_validation_badge(client, auth, admin_app):
    from swingbot import config
    _seed_trades(config.DATA_DIR, [_badged_trade(
        "t1", "win", "WEAK", exit_price=110.0, closed_at="2026-07-05T00:00:00+00:00")])
    html = client.get("/?mode=all", headers=auth).data.decode("utf-8")
    assert "WEAK" not in html
    assert "chip-tier-a" in html


def test_trade_detail_page_still_shows_the_validation_badge(client, auth, admin_app):
    from swingbot import config
    _seed_trades(config.DATA_DIR, [_badged_trade("t1", "open", "VALIDATED")])
    html = client.get("/trades/t1", headers=auth).data.decode("utf-8")
    assert "VALIDATED" in html
