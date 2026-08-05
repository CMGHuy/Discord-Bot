"""The Trade History paginator must count trade rows, and only trade rows.

Reported as "the first page shows only a few trades, but page 2 shows the full
'Show N per page'". The cause was in the row set, not the pagination maths:

  * the template emits a SECOND <tr> after any trade with more than one leg,
    to show the scale-out detail;
  * `allRows` was built with `querySelectorAll('#closed-trades-table tbody tr')`
    -- a descendant match that picked those rows up too;
  * `render()` then did `r.querySelector('.row-num').textContent = ...` on
    every row in the page slice, and a leg row has no `.row-num`, so the
    lookup returned null, `.textContent` threw a TypeError, and the forEach
    aborted -- leaving every row after the first multi-leg trade hidden.

Multi-leg trades are recent (v2 scale-out), so under the default
newest-first sort they cluster at the top: page one broke, later pages did
not. These tests pin the markup contract the JS now relies on.
"""
import json
import re


def _seed(tmp_dir, trades):
    (tmp_dir / "trades.json").write_text(json.dumps(trades), encoding="utf-8")


def _legs():
    """Two legs, in the shape the template actually reads: `fraction`
    (0-1), `exit_price` and `r`. A one-leg trade emits no detail row --
    the template requires `legs | length > 1`."""
    return [{"fraction": 0.5, "exit_price": 105.0, "r": 1.0},
            {"fraction": 0.5, "exit_price": 110.0, "r": 2.0}]


def _trade(tid, ticker="AAPL", legs=None):
    t = {
        "id": tid, "ticker": ticker, "strategy": "RSI", "horizon_key": "4w",
        "direction": "bullish", "status": "win", "confidence_level": 4,
        "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
        "opened_at": "2026-08-01T10:00:00+00:00",
        "closed_at": "2026-08-02T10:00:00+00:00",
    }
    if legs:
        t["legs"] = legs
    return t


def _tbody(html):
    assert "<tbody" in html, "closed-trades table markup missing"
    return html.split("<tbody", 1)[1].split("</tbody>", 1)[0]


def _rows(html):
    return re.findall(r"<tr\b[^>]*>", _tbody(html))


def _fetch(client, auth):
    r = client.get("/dashboard/fragment?part=history", headers=auth)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def test_a_multi_leg_trade_emits_a_tagged_detail_row(client, auth, tmp_path):
    """The extra row is legitimate -- it just has to be identifiable."""
    _seed(tmp_path, [_trade("t1", legs=_legs())])
    rows = _rows(_fetch(client, auth))
    trade_rows = [r for r in rows if "ct-row-" in r]
    leg_rows = [r for r in rows if "ct-legs-row" in r]
    assert len(trade_rows) == 1
    assert len(leg_rows) == 1
    assert 'data-legs-for="t1"' in leg_rows[0]


def test_every_tbody_row_is_either_a_trade_row_or_a_tagged_leg_row(client, auth, tmp_path):
    """The invariant the paginator depends on. A future third kind of row
    would silently rejoin the row set and reintroduce the bug."""
    _seed(tmp_path, [
        _trade("t1", "AAPL", legs=_legs()),
        _trade("t2", "MSFT"),
        _trade("t3", "TSLA", legs=_legs()),
    ])
    rows = _rows(_fetch(client, auth))
    unclassified = [r for r in rows
                    if "ct-row-" not in r and "ct-legs-row" not in r]
    assert unclassified == [], f"unclassified rows in tbody: {unclassified}"


def test_only_trade_rows_carry_row_num(client, auth, tmp_path):
    """`.row-num` presence is exactly what render() assumes, so the count of
    row-num spans must equal the count of trade rows -- never the raw <tr>
    count."""
    _seed(tmp_path, [
        _trade("t1", "AAPL", legs=_legs()),
        _trade("t2", "MSFT"),
    ])
    html = _fetch(client, auth)
    body = _tbody(html)
    trade_rows = [r for r in _rows(html) if "ct-row-" in r]
    assert len(re.findall(r'class="row-num"', body)) == len(trade_rows) == 2


def test_the_paginator_selects_trade_rows_by_id_prefix(client, auth):
    """A bare `tbody tr` selector is what pulled leg rows in. If someone
    reverts this, the TypeError comes back."""
    html = _fetch(client, auth)
    assert 'tr[id^="ct-row-"]' in html, (
        "the closed-trades paginator no longer scopes its row set to trade "
        "rows -- scale-out detail rows will re-enter the paginated slice"
    )
    assert "querySelectorAll('#closed-trades-table tbody tr')" not in html


def test_the_row_num_write_is_guarded(client, auth):
    """Defence in depth: even with the row set scoped, the write should not
    be able to abort the loop and blank the rest of the page."""
    html = _fetch(client, auth)
    assert re.search(r"var num = r\.querySelector\('\.row-num'\);\s*\n\s*if \(num\)", html), \
        "the .row-num write is unguarded again"


def test_leg_rows_move_with_their_parent_when_sorting(client, auth):
    """sortClosedTable re-appends rows to the tbody. Moving trade rows alone
    would strand each leg row under whatever trade ended up above it."""
    html = _fetch(client, auth)
    assert "var pairs = allRows.map(" in html
    assert re.search(r"tbody\.appendChild\(p\[0\]\);\s*\n\s*if \(p\[1\]\) tbody\.appendChild\(p\[1\]\);", html)
