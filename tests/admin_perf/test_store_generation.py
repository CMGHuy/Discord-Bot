"""v218 V218-2: process-wide change generations behind the admin snapshot (v205 L2-b)."""
import ast
import logging
import pathlib
import threading

import pytest

from swingbot.core.infra import store_generation as sg

SOURCE = pathlib.Path(sg.__file__)


@pytest.fixture(autouse=True)
def _clean():
    sg.reset()
    yield
    sg.reset()


def test_concerns_are_trades_journal_settings_and_start_at_zero():
    assert sg.CONCERNS == ("trades", "journal", "settings")
    assert sg.token() == (0, 0, 0)
    assert sg.connected() is False


def test_bump_moves_one_concern_and_returns_its_new_value():
    assert sg.bump("journal") == 1
    assert sg.bump("journal") == 2
    assert sg.generation("journal") == 2
    assert sg.token() == (0, 2, 0)


def test_an_unknown_concern_is_refused():
    with pytest.raises(KeyError):
        sg.bump("market")
    with pytest.raises(KeyError):
        sg.generation("market")


def test_bump_all_moves_every_concern():
    sg.bump("trades")
    sg.bump_all()
    assert sg.token() == (2, 1, 1)


def test_reset_zeroes_counters_and_clears_connected():
    sg.bump_all()
    sg.set_connected(True)
    sg.reset()
    assert sg.token() == (0, 0, 0) and sg.connected() is False


def test_set_connected_logs_each_transition_once(caplog):
    caplog.set_level(logging.INFO, logger=sg.log.name)
    sg.set_connected(True)
    sg.set_connected(True)
    sg.set_connected(False)
    sg.set_connected(False)
    lines = [r.getMessage() for r in caplog.records if r.name == sg.log.name]
    assert len(lines) == 2
    assert "connected" in lines[0] and "bypassed" in lines[1]


def test_concurrent_bumps_are_not_lost():
    def worker():
        for _ in range(500):
            sg.bump("trades")
    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sg.generation("trades") == 4000


def test_the_module_is_a_leaf():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not {name for name in imported if name.startswith(("swingbot", "flask"))}
