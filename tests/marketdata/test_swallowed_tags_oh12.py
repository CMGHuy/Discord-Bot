"""v148 OH12: marketdata data/data_refresh handlers count under their tags."""
import pytest

from swingbot.core.infra import swallowed as sw
from swingbot.core.marketdata import data, data_refresh


def _boom(*a, **k):
    raise RuntimeError("probe")


class _FastInfo:
    def get(self, attr):
        raise KeyError(attr)


@pytest.fixture(autouse=True)
def _clean():
    sw.reset()
    yield
    sw.reset()


def test_fast_info_price_counts_each_attribute_and_returns_none():
    assert data._fast_info_price(_FastInfo()) is None
    assert sw.snapshot()["marketdata.fast_info_price"]["count"] == 7


def test_price_batch_failure_is_counted_and_returns_empty(monkeypatch):
    monkeypatch.setattr(data.yf_safe, "download", _boom)
    assert data._yf_batch_prices(["AAA", "BBB"]) == {}
    assert sw.snapshot()["marketdata.price_batch"]["last_error"] == "RuntimeError: probe"


def test_record_coverage_failure_is_counted_and_record_still_written(monkeypatch, tmp_path):
    monkeypatch.setattr(data_refresh, "load_from_disk", _boom)
    state = {}
    data_refresh._record(state, "AAA", "daily", {"status": "fresh", "rows": 1}, str(tmp_path))
    assert state
    assert sw.snapshot()["marketdata.record_coverage"]["count"] == 1
