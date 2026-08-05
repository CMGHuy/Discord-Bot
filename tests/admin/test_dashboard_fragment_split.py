"""The dashboard fragment must return a fragment -- never a whole HTML page.

Two defects, reported together and fixed together:

1. **An expired session turned the poll into a page.** `require_auth`
   redirected to /login, and `fetch()` follows redirects transparently, so the
   dashboard's 5s poll received a 200 carrying a complete login document. Its
   morphdom then patched that over the stat cards and tables, and the page
   appeared to lose every open trade and all history under any filter. The
   client only ever checked for 401, which a redirect never produces.

2. **The poll shipped the entire history table.** The fragment carried up to
   CLOSED_TRADES_FRAGMENT_LIMIT closed-trade rows (~1.8 MB) every five seconds
   in order to patch a few hundred bytes of stats.
"""


def _is_full_page(body: str) -> bool:
    return body.lstrip().lower().startswith("<!doctype")


def test_unauthenticated_fragment_returns_401_not_a_login_page(client):
    """The regression that made the dashboard look empty."""
    r = client.get("/dashboard/fragment?part=live")
    assert r.status_code == 401
    assert not _is_full_page(r.get_data(as_text=True))
    assert b"<html" not in r.data.lower()


def test_unauthenticated_fragment_sends_no_basic_auth_challenge(client):
    """A WWW-Authenticate header here would pop the browser's native
    Basic-Auth dialog on top of the dashboard. The client wants to reload
    into the app's own login page instead."""
    r = client.get("/dashboard/fragment")
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") is None


def test_a_top_level_page_still_redirects_to_login(client):
    """Only *fragment* requests changed. A real navigation must still land on
    the login page, or an unauthenticated visitor gets a bare 401 body."""
    r = client.get("/")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_xhr_header_also_counts_as_a_partial(client):
    """Not every partial lives under a /fragment path -- honor the header too."""
    r = client.get("/", headers={"X-Requested-With": "XMLHttpRequest"})
    assert r.status_code == 401


def test_live_part_excludes_the_history_table(client, auth):
    live = client.get("/dashboard/fragment?part=live", headers=auth).get_data(as_text=True)
    assert "dashboard-history" not in live
    assert 'id="closed-trades-table"' not in live
    assert not _is_full_page(live)


def test_history_part_carries_the_closed_trades_table(client, auth):
    hist = client.get("/dashboard/fragment?part=history", headers=auth).get_data(as_text=True)
    assert 'id="closed-trades-table"' in hist
    assert not _is_full_page(hist)


def test_all_is_the_default_and_still_carries_both_halves(client, auth):
    """The initial page load and any older caller must keep working."""
    default = client.get("/dashboard/fragment", headers=auth).get_data(as_text=True)
    explicit = client.get("/dashboard/fragment?part=all", headers=auth).get_data(as_text=True)
    assert 'id="closed-trades-table"' in default
    assert "dashboard-live" in default and "dashboard-history" in default
    assert default == explicit


def test_an_unknown_part_falls_back_to_all_rather_than_erroring(client, auth):
    r = client.get("/dashboard/fragment?part=nonsense", headers=auth)
    assert r.status_code == 200
    assert 'id="closed-trades-table"' in r.get_data(as_text=True)


def test_live_is_dramatically_smaller_than_the_whole_fragment(client, auth):
    """The point of the split. Not a micro-benchmark -- an order-of-magnitude
    assertion that the poll stopped carrying the history table."""
    live = client.get("/dashboard/fragment?part=live", headers=auth).data
    everything = client.get("/dashboard/fragment?part=all", headers=auth).data
    assert len(live) < len(everything)


def test_etag_varies_by_part(client, auth):
    """Same URL path, different bodies. Sharing one ETag would let a live poll
    304 away the history response (and vice versa)."""
    live = client.get("/dashboard/fragment?part=live", headers=auth)
    hist = client.get("/dashboard/fragment?part=history", headers=auth)
    assert live.headers["ETag"] != hist.headers["ETag"]


def test_a_live_etag_does_not_304_the_history_response(client, auth):
    """The failure that ETag collision would actually cause."""
    live_etag = client.get("/dashboard/fragment?part=live", headers=auth).headers["ETag"]
    r = client.get("/dashboard/fragment?part=history",
                   headers={**auth, "If-None-Match": live_etag})
    assert r.status_code == 200
    assert 'id="closed-trades-table"' in r.get_data(as_text=True)


def test_each_part_still_304s_against_its_own_etag(client, auth):
    for part in ("live", "history", "all"):
        etag = client.get(f"/dashboard/fragment?part={part}", headers=auth).headers["ETag"]
        r = client.get(f"/dashboard/fragment?part={part}",
                       headers={**auth, "If-None-Match": etag})
        assert r.status_code == 304, part
        assert r.data == b""
