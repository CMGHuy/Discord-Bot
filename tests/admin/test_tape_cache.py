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


def test_concurrent_overlapping_lists_fetch_the_uncovered_symbols():
    cache = SingleFlightCache(ttl=30)
    started = threading.Event()
    release = threading.Event()
    calls = []
    results = {}

    def fetch(symbols):
        calls.append(list(symbols))
        if symbols == ["A", "B"]:
            started.set()
            assert release.wait(5)
        return {s: 1.0 for s in symbols}

    first = threading.Thread(target=lambda: results.update(first=cache.get(["A", "B"], fetch)))
    second = threading.Thread(target=lambda: results.update(second=cache.get(["B", "C"], fetch)))
    first.start()
    assert started.wait(5)
    second.start()
    time.sleep(0.05)
    release.set()
    first.join(5)
    second.join(5)

    assert not first.is_alive() and not second.is_alive()
    assert calls == [["A", "B"], ["C"]]
    assert results["second"] == {"B": 1.0, "C": 1.0}


def test_three_overlapping_callers_wait_through_successive_flights():
    cache = SingleFlightCache(ttl=30)
    first_started = threading.Event()
    release_first = threading.Event()
    next_started = threading.Event()
    release_next = threading.Event()
    calls = []
    results = {}

    def fetch(symbols):
        calls.append(list(symbols))
        if symbols == ["A", "B"]:
            first_started.set()
            assert release_first.wait(5)
        else:
            next_started.set()
            assert release_next.wait(5)
        return {s: 1.0 for s in symbols}

    threads = [
        threading.Thread(target=lambda: results.update(first=cache.get(["A", "B"], fetch))),
        threading.Thread(target=lambda: results.update(second=cache.get(["B", "C"], fetch))),
        threading.Thread(target=lambda: results.update(third=cache.get(["B", "D"], fetch))),
    ]
    threads[0].start()
    assert first_started.wait(5)
    threads[1].start()
    threads[2].start()
    time.sleep(0.05)
    release_first.set()
    assert next_started.wait(5)
    time.sleep(0.05)
    release_next.set()
    for thread in threads:
        thread.join(5)

    assert all(not thread.is_alive() for thread in threads)
    assert calls[0] == ["A", "B"]
    assert {tuple(call) for call in calls[1:]} == {("C",), ("D",)}
    assert results["second"] == {"B": 1.0, "C": 1.0}
    assert results["third"] == {"B": 1.0, "D": 1.0}


def test_fresh_entry_returns_while_an_unrelated_fetch_is_running():
    cache = SingleFlightCache(ttl=30, wait=2.0)
    cache.get(["A"], lambda symbols: {"A": 1.0})
    started = threading.Event()
    release = threading.Event()
    reader_started = threading.Event()
    answered = threading.Event()
    result = {}

    def blocked_fetch(symbols):
        started.set()
        assert release.wait(5)
        return {"B": 2.0}

    def read_cached():
        reader_started.set()
        result.update(cache.get(["A"], blocked_fetch))
        answered.set()

    leader = threading.Thread(target=lambda: cache.get(["B"], blocked_fetch))
    reader = threading.Thread(target=read_cached)
    leader.start()
    assert started.wait(5)
    reader.start()
    try:
        assert reader_started.wait(5)
        assert answered.wait(0.5)
        assert result == {"A": 1.0}
    finally:
        release.set()
        reader.join(5)
        leader.join(5)


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
