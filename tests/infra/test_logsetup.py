"""v111 §1-§2: one root logging setup and the scan-id context."""
import asyncio
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler

from swingbot.core.infra.logsetup import (
    LOG_FORMAT, apply_log_level, configure_logging, new_scan_id, scan_context,
    scan_id_var, with_current_context)


def _owned(root):
    return [h for h in root.handlers if getattr(h, "_swingbot_logsetup", False)]


def _lines(root, path, marker):
    for handler in _owned(root):
        handler.flush()
    return [line for line in path.read_text().splitlines() if marker in line]


def test_format_carries_level_scan_id_and_logger_name():
    assert "[%(levelname)s]" in LOG_FORMAT
    assert "[%(scan_id)s]" in LOG_FORMAT
    assert "%(name)s:" in LOG_FORMAT
    # The admin Logs page finds the level as the FIRST [WORD] on a line
    # (frontend system.store.ts LEVEL_PATTERN); the level must stay first.
    assert LOG_FORMAT.index("%(levelname)s") < LOG_FORMAT.index("%(scan_id)s")


def test_configure_logging_is_idempotent(tmp_path, restore_root_logging):
    for _ in range(2):
        configure_logging(str(tmp_path / "bot.log"), "INFO", max_bytes=1024, backups=1)
    owned = _owned(restore_root_logging)
    assert len(owned) == 2
    assert sum(isinstance(h, RotatingFileHandler) for h in owned) == 1


def test_a_line_shows_level_scan_id_and_logger_name(tmp_path, restore_root_logging):
    path = tmp_path / "bot.log"
    configure_logging(str(path), "INFO", max_bytes=1 << 20, backups=1)
    logger = logging.getLogger("swingbot.test_logsetup")
    logger.info("outside")
    with scan_context("s-1405ab"):
        logger.info("inside")
    outside, inside = _lines(restore_root_logging, path, "swingbot.test_logsetup")
    assert re.search(r"\[INFO\] \[-\] swingbot\.test_logsetup: outside$", outside)
    assert re.search(r"\[INFO\] \[s-1405ab\] swingbot\.test_logsetup: inside$", inside)


def test_scan_id_is_dash_outside_and_the_id_inside():
    assert scan_id_var.get() == "-"
    with scan_context("s-0000aa") as sid:
        assert sid == "s-0000aa"
        assert scan_id_var.get() == "s-0000aa"
    assert scan_id_var.get() == "-"


def test_to_thread_work_inside_a_scan_carries_the_id():
    async def scan():
        with scan_context("s-0900zz"):
            return await asyncio.to_thread(scan_id_var.get)

    assert asyncio.run(scan()) == "s-0900zz"


def test_pool_work_wrapped_with_the_current_context_carries_the_id():
    with scan_context("s-0901q7"):
        task = with_current_context(scan_id_var.get)
        with ThreadPoolExecutor(max_workers=3) as pool:
            got = list(pool.map(lambda _: task(), range(6)))
    assert got == ["s-0901q7"] * 6


def test_a_bare_pool_does_not_carry_the_id():
    # Pins why with_current_context exists: ThreadPoolExecutor threads start
    # in an empty context, so unwrapped pool work logs as "-".
    with scan_context("s-0902aa"):
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(scan_id_var.get).result() == "-"


def test_apply_log_level_changes_the_effective_level(restore_root_logging):
    apply_log_level("DEBUG")
    assert logging.getLogger("swingbot.anything").getEffectiveLevel() == logging.DEBUG
    apply_log_level("warning")
    assert logging.getLogger().level == logging.WARNING
    assert apply_log_level(logging.ERROR) == logging.ERROR
    assert apply_log_level("NOT-A-LEVEL") == logging.INFO   # bot_core's old fallback


def test_new_scan_id_is_s_hhmm_plus_two_characters():
    at_1405 = time.mktime((2026, 9, 28, 14, 5, 0, 0, 0, -1))
    assert re.fullmatch(r"s-1405[a-z0-9]{2}", new_scan_id(at_1405))
    assert re.fullmatch(r"s-\d{4}[a-z0-9]{2}", new_scan_id())
