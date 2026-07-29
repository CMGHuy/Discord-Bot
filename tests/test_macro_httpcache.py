import os
import time

import pytest

import swingbot.core.macro.httpcache as httpcache


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(httpcache, "CACHE_DIR", str(tmp_path))
    httpcache.LAST_SERVED_STALE = False
    return tmp_path


def _counting_get(payload):
    calls = {"n": 0}

    def fake_get(url, params=None, timeout=None):
        calls["n"] += 1
        return _Resp(payload)
    return fake_get, calls


def test_fresh_cache_skips_network(cache_dir, monkeypatch):
    fake_get, calls = _counting_get({"v": 1})
    monkeypatch.setattr(httpcache.requests, "get", fake_get)
    assert httpcache.fetch_json("https://x.test/a", ttl_s=3600) == {"v": 1}
    assert httpcache.fetch_json("https://x.test/a", ttl_s=3600) == {"v": 1}
    assert calls["n"] == 1


def test_expired_cache_refetches(cache_dir, monkeypatch):
    fake_get, calls = _counting_get({"v": 1})
    monkeypatch.setattr(httpcache.requests, "get", fake_get)
    httpcache.fetch_json("https://x.test/a", ttl_s=0)
    httpcache.fetch_json("https://x.test/a", ttl_s=0)
    assert calls["n"] == 2


def test_failure_serves_stale_and_flags(cache_dir, monkeypatch):
    fake_get, _ = _counting_get({"v": 1})
    monkeypatch.setattr(httpcache.requests, "get", fake_get)
    httpcache.fetch_json("https://x.test/a", ttl_s=0)

    def boom(url, params=None, timeout=None):
        raise OSError("network down")
    monkeypatch.setattr(httpcache.requests, "get", boom)
    assert httpcache.fetch_json("https://x.test/a", ttl_s=0) == {"v": 1}
    assert httpcache.LAST_SERVED_STALE is True


def test_failure_without_cache_returns_none(cache_dir, monkeypatch):
    def boom(url, params=None, timeout=None):
        raise OSError("network down")
    monkeypatch.setattr(httpcache.requests, "get", boom)
    assert httpcache.fetch_json("https://x.test/never") is None


def test_secret_params_never_reach_filenames(cache_dir, monkeypatch):
    fake_get, _ = _counting_get({"v": 1})
    monkeypatch.setattr(httpcache.requests, "get", fake_get)
    httpcache.fetch_json("https://x.test/a", params={"api_key": "SECRET123"})
    names = "".join(os.listdir(cache_dir))
    assert "SECRET123" not in names            # keys are sha1-hashed (secrets contract)


def test_purge_removes_only_old(cache_dir, monkeypatch):
    fake_get, _ = _counting_get({"v": 1})
    monkeypatch.setattr(httpcache.requests, "get", fake_get)
    httpcache.fetch_json("https://x.test/old")
    httpcache.fetch_json("https://x.test/new")
    old_file = sorted(cache_dir.iterdir())[0]
    past = time.time() - 40 * 86400
    os.utime(old_file, (past, past))
    assert httpcache.purge_cache(max_age_days=30) == 1
    assert len(list(cache_dir.iterdir())) == 1
