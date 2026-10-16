"""v148 O5: the swallowed-error counter -- per-tag counts, merge, thread
safety, and a log record identical to the one the handler emitted before."""
import ast
import datetime as dt
import logging
import pathlib
import threading
from unittest.mock import patch

import pytest

from swingbot.core.infra import swallowed as swallowed_mod
from swingbot.core.infra.swallowed import swallowed

LOG = logging.getLogger("tests.infra.swallowed_site")
MODULE_PATH = pathlib.Path(swallowed_mod.__file__)


@pytest.fixture(autouse=True)
def _clean_counts():
    swallowed_mod.reset()
    yield
    swallowed_mod.reset()


def _site(level=logging.WARNING, exc_info=False):
    """A converted handler, as production code writes it."""
    try:
        raise ValueError("boom")
    except ValueError as exc:
        swallowed(LOG, "test.site", exc, "fetch %s failed", "AAPL",
                  level=level, exc_info=exc_info)


def _records(caplog):
    return [r for r in caplog.records if r.name == LOG.name]


def test_counts_per_tag_with_first_and_last_seen():
    swallowed(LOG, "a.one", ValueError("x"))
    swallowed(LOG, "a.one", KeyError("y"))
    swallowed(LOG, "b.two", RuntimeError("z"))

    snap = swallowed_mod.snapshot()

    assert snap["a.one"]["count"] == 2
    assert snap["b.two"]["count"] == 1
    assert snap["a.one"]["last_error"] == "KeyError: 'y'"
    assert snap["a.one"]["first_at"] <= snap["a.one"]["last_at"]


def test_last_error_is_type_and_message_truncated_to_200():
    swallowed(LOG, "a.long", ValueError("v" * 500))

    last_error = swallowed_mod.snapshot()["a.long"]["last_error"]

    assert last_error.startswith("ValueError: vvv")
    assert len(last_error) == 200


def test_record_keeps_message_level_and_points_at_the_caller(caplog):
    with caplog.at_level(logging.DEBUG, logger=LOG.name):
        _site()

    [record] = _records(caplog)
    assert record.levelno == logging.WARNING
    assert record.getMessage() == "fetch AAPL failed"
    assert record.swallowed_tag == "test.site"
    assert record.funcName == "_site"
    assert record.exc_info is None


def test_error_with_exc_info_matches_log_exception(caplog):
    with caplog.at_level(logging.DEBUG, logger=LOG.name):
        try:
            raise ValueError("boom")
        except ValueError:
            LOG.exception("fetch %s failed", "AAPL")
        _site(level=logging.ERROR, exc_info=True)

    before, after = _records(caplog)
    assert (before.levelno, before.getMessage()) == (after.levelno, after.getMessage())
    assert after.exc_info is not None and after.exc_info[0] is ValueError


def test_a_site_that_logged_nothing_logs_the_tag_at_its_level(caplog):
    with caplog.at_level(logging.DEBUG, logger=LOG.name):
        swallowed(LOG, "a.quiet", ValueError("boom"), level=logging.DEBUG)

    [record] = _records(caplog)
    assert record.levelno == logging.DEBUG
    assert record.getMessage() == "swallowed a.quiet: ValueError: boom"


def test_a_patched_level_method_still_sees_the_call():
    with patch.object(LOG, "warning") as warning:
        _site()

    warning.assert_called_once()
    assert warning.call_args.args == ("fetch %s failed", "AAPL")
    assert warning.call_args.kwargs["extra"] == {"swallowed_tag": "test.site"}


def test_a_non_standard_level_goes_through_log_log(caplog):
    with caplog.at_level(1, logger=LOG.name):
        swallowed(LOG, "a.odd", ValueError("boom"), "odd %s", "level", level=25)

    [record] = _records(caplog)
    assert record.levelno == 25 and record.getMessage() == "odd level"


def test_merge_adds_counts_and_widens_the_span():
    swallowed_mod.merge({"a.one": {"count": 2, "first_at": "2026-10-01T00:00:00+00:00",
                                   "last_at": "2026-10-01T01:00:00+00:00",
                                   "last_error": "ValueError: old"}})
    swallowed_mod.merge({"a.one": {"count": 3, "first_at": "2026-10-01T02:00:00+00:00",
                                   "last_at": "2026-10-01T03:00:00+00:00",
                                   "last_error": "ValueError: new"}})

    entry = swallowed_mod.snapshot()["a.one"]

    assert entry == {"count": 5, "first_at": "2026-10-01T00:00:00+00:00",
                     "last_at": "2026-10-01T03:00:00+00:00", "last_error": "ValueError: new"}


def test_merge_of_an_older_entry_keeps_the_newer_last_error():
    swallowed(LOG, "a.one", ValueError("now"))
    swallowed_mod.merge({"a.one": {"count": 1, "first_at": "2000-01-01T00:00:00+00:00",
                                   "last_at": "2000-01-01T00:00:00+00:00",
                                   "last_error": "ValueError: ancient"}})

    entry = swallowed_mod.snapshot()["a.one"]

    assert entry["count"] == 2
    assert entry["first_at"] == "2000-01-01T00:00:00+00:00"
    assert entry["last_error"] == "ValueError: now"


def test_merge_of_nothing_changes_nothing():
    swallowed_mod.merge({})
    swallowed_mod.merge(None)
    assert swallowed_mod.snapshot() == {}


def test_snapshot_is_a_copy():
    swallowed(LOG, "a.one", ValueError("x"))
    snap = swallowed_mod.snapshot()
    snap["a.one"]["count"] = 99
    assert swallowed_mod.snapshot()["a.one"]["count"] == 1


def test_counting_is_thread_safe():
    def hammer():
        for _ in range(500):
            swallowed(LOG, "a.threads", ValueError("x"), level=logging.DEBUG)

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert swallowed_mod.snapshot()["a.threads"]["count"] == 4000


def test_started_at_is_a_utc_iso_timestamp():
    parsed = dt.datetime.fromisoformat(swallowed_mod.STARTED_AT)
    assert parsed.utcoffset() == dt.timedelta(0)


def test_module_is_a_leaf():
    """Spawned fetch children and runstate import it; a swingbot import here
    could close a cycle."""
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                for alias in node.names]
    imported += [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not [name for name in imported if name.startswith("swingbot")]


# ---------------------------------------------------------------------------
# OH7: _run_bounded carries a spawned child's counts back to the parent
# ---------------------------------------------------------------------------

class _InlinePool:
    """In-process stand-in for ProcessPoolExecutor: runs the submitted
    callable here, like tests/scanning/conftest.py's _InlineProcessPool."""

    def __init__(self, max_workers=None, mp_context=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *args):
        from concurrent.futures import Future
        future = Future()
        try:
            future.set_result(fn(*args))
        except Exception as exc:
            future.set_exception(exc)
        return future


def _boom(_x):
    raise RuntimeError("child exploded")


def _probe():
    from tests.infra import swallowed_probe
    return swallowed_probe


def test_counted_call_in_the_parent_returns_no_counts():
    from swingbot.core.scanning import fetch

    assert fetch._counted_call(_probe().count_then_return, 21) == (42, {})
    assert swallowed_mod.snapshot()["probe.count_then_return"]["count"] == 2


def test_counted_call_in_a_child_returns_its_snapshot(monkeypatch):
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(fetch.multiprocessing, "parent_process", lambda: object())

    result, counts = fetch._counted_call(_probe().count_then_return, 21)

    assert result == 42
    assert counts["probe.count_then_return"]["count"] == 2


def test_inline_pool_keeps_the_return_shape_and_counts_once(monkeypatch):
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)

    assert fetch._run_bounded(_probe().count_then_return, (21,), 5, "probe") == 42
    assert fetch._run_bounded(dict, (), 5, "probe-dict") == {}
    assert swallowed_mod.snapshot()["probe.count_then_return"]["count"] == 2


def test_a_raising_child_is_counted_under_run_bounded(monkeypatch, caplog):
    from swingbot.core.scanning import fetch
    monkeypatch.setattr(fetch, "ProcessPoolExecutor", _InlinePool)

    with caplog.at_level(logging.ERROR, logger=fetch.log.name):
        assert fetch._run_bounded(_boom, (1,), 5, "probe-fail") is None

    entry = swallowed_mod.snapshot()["scan.run_bounded"]
    assert entry["count"] == 1 and entry["last_error"] == "RuntimeError: child exploded"
    [record] = [r for r in caplog.records if r.name == fetch.log.name]
    assert record.getMessage() == "probe-fail failed: child exploded"
    assert record.levelno == logging.ERROR and record.exc_info is not None


@pytest.mark.slow
def test_a_spawned_child_counts_travel_back():
    from swingbot.core.scanning import fetch

    out = fetch._run_bounded(_probe().count_then_return, (21,), 120, "probe-spawn")

    assert out == 42
    assert swallowed_mod.snapshot()["probe.count_then_return"]["count"] == 2


@pytest.mark.slow
def test_a_timeout_is_counted_under_run_bounded(caplog):
    from swingbot.core.scanning import fetch

    with caplog.at_level(logging.ERROR, logger=fetch.log.name):
        assert fetch._run_bounded(_probe().sleep_forever, (), 0.5, "probe-stuck") is None

    entry = swallowed_mod.snapshot()["scan.run_bounded"]
    assert entry["count"] == 1 and entry["last_error"] == "TimeoutError: probe-stuck"
    assert any("probe-stuck did not finish within 0.5s" in r.getMessage()
               for r in caplog.records if r.name == fetch.log.name)
