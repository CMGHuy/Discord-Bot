"""v132: a caller with a wait limit gives up instead of queueing forever."""
import threading

import pytest

from swingbot.core.infra.retry import with_retry
from swingbot.core.marketdata import yf_safe


@pytest.fixture(autouse=True)
def _no_default():
    yield
    yf_safe.set_default_lock_timeout(None)


@pytest.fixture
def held_lock():
    yf_safe._DOWNLOAD_LOCK.acquire()
    yield
    yf_safe._DOWNLOAD_LOCK.release()


def test_explicit_limit_raises_busy_when_lock_is_held(held_lock):
    with pytest.raises(yf_safe.DownloadBusy):
        yf_safe.download("NVDA", lock_timeout=0.05)


def test_process_default_applies_when_no_argument_is_passed(held_lock):
    yf_safe.set_default_lock_timeout(0.05)
    with pytest.raises(yf_safe.DownloadBusy):
        yf_safe.download("NVDA")


def test_without_a_limit_the_caller_still_waits(monkeypatch, held_lock):
    monkeypatch.setattr("yfinance.download", lambda *a, **k: "frame")
    out = []
    t = threading.Thread(target=lambda: out.append(yf_safe.download("NVDA")))
    t.start()
    t.join(0.2)
    assert t.is_alive() and out == []          # still queued, not failed
    yf_safe._DOWNLOAD_LOCK.release()
    t.join(2)
    yf_safe._DOWNLOAD_LOCK.acquire()            # hand back to the fixture
    assert out == ["frame"]


def test_lock_is_released_after_a_limited_download(monkeypatch):
    monkeypatch.setattr("yfinance.download", lambda *a, **k: "frame")
    assert yf_safe.download("NVDA", lock_timeout=1) == "frame"
    assert yf_safe._DOWNLOAD_LOCK.acquire(blocking=False)
    yf_safe._DOWNLOAD_LOCK.release()


def test_with_retry_does_not_retry_busy(held_lock):
    calls = []

    def fn():
        calls.append(1)
        return yf_safe.download("NVDA", lock_timeout=0.01)

    with pytest.raises(yf_safe.DownloadBusy):
        with_retry(fn, attempts=3, base_delay=0)
    assert len(calls) == 1
