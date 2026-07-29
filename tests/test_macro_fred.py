import pytest

import swingbot.config as config
import swingbot.core.macro.fred as fred

FIXTURE = {"observations": [
    {"date": "2025-05-01", "value": "310.5"},
    {"date": "2025-06-01", "value": "."},          # FRED's "no data" marker
    {"date": "2025-07-01", "value": "312.0"},
    {"date": "2024-07-01", "value": "300.0"},      # out of order on purpose
]}


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(config, "FRED_API_KEY", "test-key", raising=False)


def test_series_parses_sorted_and_skips_dots(with_key, monkeypatch):
    monkeypatch.setattr(fred, "fetch_json", lambda *a, **k: FIXTURE)
    assert fred.fred_series("CPIAUCSL") == [
        ("2024-07-01", 300.0), ("2025-05-01", 310.5), ("2025-07-01", 312.0)]


def test_latest(with_key, monkeypatch):
    monkeypatch.setattr(fred, "fetch_json", lambda *a, **k: FIXTURE)
    assert fred.latest("CPIAUCSL") == ("2025-07-01", 312.0)


def test_yoy_golden(with_key, monkeypatch):
    # 13 monthly observations: yoy = (last / value-12-obs-earlier - 1) * 100
    obs = [{"date": f"2025-{m:02d}-01", "value": str(100 + m)} for m in range(1, 13)]
    obs.append({"date": "2026-01-01", "value": "113.0"})
    monkeypatch.setattr(fred, "fetch_json", lambda *a, **k: {"observations": obs})
    assert fred.yoy("X") == pytest.approx((113.0 / 101.0 - 1) * 100)


def test_release_dates(with_key, monkeypatch):
    payload = {"release_dates": [{"release_id": 10, "date": "2026-07-15"},
                                 {"release_id": 10, "date": "2026-08-12"}]}
    monkeypatch.setattr(fred, "fetch_json", lambda *a, **k: payload)
    assert fred.fred_release_dates(10) == ["2026-07-15", "2026-08-12"]


def test_no_key_means_none_and_zero_network(monkeypatch):
    monkeypatch.setattr(config, "FRED_API_KEY", "", raising=False)

    def boom(*a, **k):
        raise AssertionError("network path must not be reached without a key")
    monkeypatch.setattr(fred, "fetch_json", boom)
    assert fred.fred_series("CPIAUCSL") is None
    assert fred.fred_release_dates(10) == []
    assert fred.yoy("CPIAUCSL") is None


def test_calls_fetch_json_with_supported_kwargs_only(with_key, monkeypatch):
    """Regression: the plan passed provider="fred", a kwarg that only existed
    for the cut health ledger (G10). The other tests stub fetch_json with
    **kwargs and would not have caught the TypeError in production."""
    import inspect

    from swingbot.core.macro import httpcache

    seen = {}

    def spy(url, **kw):
        seen.update(kw)
        return FIXTURE
    monkeypatch.setattr(fred, "fetch_json", spy)
    fred.fred_series("CPIAUCSL")
    fred.fred_release_dates(10)

    allowed = set(inspect.signature(httpcache.fetch_json).parameters) - {"url"}
    assert set(seen) <= allowed, f"unsupported kwargs: {set(seen) - allowed}"
