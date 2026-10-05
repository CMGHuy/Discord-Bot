"""SingleFlightCache -- one download per expiry, however many callers."""
import threading
import time

from swingbot.admin.tape_cache import SingleFlightCache


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_concurrent_callers_share_one_fetch():
    calls = []
    release = threading.Event()

    def fetch(symbols):
        calls.append(list(symbols))
        release.wait(5)
        return {s: 1.0 for s in symbols}

    cache = SingleFlightCache(ttl=30)
    results = []
    threads = [threading.Thread(target=lambda: results.append(cache.get(["A", "B"], fetch)))
               for _ in range(20)]
    for t in threads:
        t.start()
    time.sleep(0.2)
    release.set()
    for t in threads:
        t.join(5)
    assert calls == [["A", "B"]]
    assert results == [{"A": 1.0, "B": 1.0}] * 20


def test_fresh_entries_skip_the_fetch_and_overlapping_lists_share():
    calls = []

    def fetch(symbols):
        calls.append(list(symbols))
        return {s: 2.0 for s in symbols}

    cache = SingleFlightCache(ttl=30, clock=_Clock())
    cache.get(["A", "B"], fetch)
    assert cache.get(["B", "C"], fetch) == {"B": 2.0, "C": 2.0}
    assert calls == [["A", "B"], ["C"]]


def test_failed_fetch_is_not_cached():
    answers = iter([{}, {"A": 3.0}])
    cache = SingleFlightCache(ttl=30, clock=_Clock())
    assert cache.get(["A"], lambda s: next(answers)) == {}
    assert cache.get(["A"], lambda s: next(answers)) == {"A": 3.0}


def test_expired_entry_survives_a_failed_refetch():
    clock = _Clock()
    cache = SingleFlightCache(ttl=30, clock=clock)
    cache.get(["A"], lambda s: {"A": 4.0})
    clock.now = 31.0

    def boom(symbols):
        raise RuntimeError("yahoo down")

    assert cache.get(["A"], boom) == {"A": 4.0}
