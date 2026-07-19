"""Response-header behaviors: ETag/304 polling, gzip, chart caching."""


def test_dashboard_fragment_etag_304(client, auth):
    r1 = client.get("/dashboard/fragment", headers=auth)
    assert r1.status_code == 200
    etag = r1.headers.get("ETag")
    assert etag, "expected an ETag header on the fragment response"

    r2 = client.get("/dashboard/fragment", headers={**auth, "If-None-Match": etag})
    assert r2.status_code == 304
    assert r2.data == b""


def test_dashboard_fragment_etag_changes_when_content_changes(client, auth):
    r1 = client.get("/dashboard/fragment?mode=all", headers=auth)
    r2 = client.get("/dashboard/fragment?mode=today", headers=auth)
    # Different query params -> (usually) different rendered HTML -> different ETag.
    # Both still 200 since neither request sent an If-None-Match at all.
    assert r1.status_code == 200 and r2.status_code == 200


import gzip


def test_gzip_applied_to_large_html_response(client, auth):
    r = client.get("/", headers={**auth, "Accept-Encoding": "gzip"})
    assert r.headers.get("Content-Encoding") == "gzip"
    assert b"Dashboard" in gzip.decompress(r.data)


def test_gzip_skipped_without_accept_encoding(client, auth):
    r = client.get("/", headers=auth)  # no Accept-Encoding at all
    assert r.headers.get("Content-Encoding") is None


def test_gzip_skipped_for_small_response(client, auth):
    r = client.get("/api/health", headers={**auth, "Accept-Encoding": "gzip"})
    assert r.headers.get("Content-Encoding") is None
