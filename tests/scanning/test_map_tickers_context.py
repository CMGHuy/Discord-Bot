"""v111 §2: map_tickers' pool workers log with the caller's scan id."""
from swingbot.core.infra.logsetup import scan_context, scan_id_var
from swingbot.core.scanning import fetch


def test_pool_workers_inherit_the_scan_id():
    with scan_context("s-1111ab"):
        got = fetch.map_tickers(lambda t: scan_id_var.get(), ["A", "B", "C", "D"], workers=3)
    assert got == ["s-1111ab"] * 4


def test_serial_path_is_unchanged():
    with scan_context("s-1112ab"):
        got = fetch.map_tickers(lambda t: (t, scan_id_var.get()), ["A"], workers=1)
    assert got == [("A", "s-1112ab")]
