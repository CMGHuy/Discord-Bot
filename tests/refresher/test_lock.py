"""v201: only one refresher fetches (Postgres session advisory lock)."""
from swingbot.refresher import lock


def test_second_holder_is_refused_until_the_first_releases():
    with lock.single_instance() as first:
        with lock.single_instance() as second:
            assert (first, second) == (True, False)
    with lock.single_instance() as again:
        assert again is True
    assert lock.ADVISORY_LOCK_KEY == 201001
