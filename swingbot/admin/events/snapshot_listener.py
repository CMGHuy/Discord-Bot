"""The admin snapshot's own LISTEN connection (v218, v205 L2-b).

The SSE broker's DbEventListener runs only while a browser tab is subscribed
(broker.subscribe/_release), so it cannot vouch for a snapshot read by a cold
GET. This listener is a separate per-process singleton on channels ``trades``
(trades, plans, starred_plans triggers) and ``journal`` (journal_entries). It
emits nothing; each NOTIFY bumps that concern's generation in
``store_generation`` before the debounce. A (re)connect bumps every generation,
since NOTIFYs sent while the connection was down are gone, and a lost
connection clears ``store_generation.connected()`` so the snapshot is bypassed.

Started lazily on the admin's first non-testing request (gunicorn runs
``preload_app = False``, so the thread lives in the worker), never in tests
unless a test calls ``ensure_started`` with an injected ``listen=`` fake.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from flask import Flask, current_app

from swingbot import config
from swingbot.core.infra import store_generation
from swingbot.core.infra.swallowed import swallowed

from .db_listener import DbEventListener

log = logging.getLogger(__name__)

SNAPSHOT_CHANNELS: tuple[str, ...] = ("trades", "journal")

_lock = threading.Lock()
_listener: "SnapshotListener | None" = None


class SnapshotListener(DbEventListener):
    """Turn ``trades``/``journal`` NOTIFYs into store-generation bumps."""

    def __init__(self, **kwargs):
        super().__init__(lambda _name: None, channels=SNAPSHOT_CHANNELS, **kwargs)

    def on_notification(self, channel: str) -> None:
        super().on_notification(channel)
        if channel in SNAPSHOT_CHANNELS:
            store_generation.bump(channel)

    def _on_listening(self) -> None:
        super()._on_listening()
        store_generation.bump_all()          # before connected: no request sees the old token as valid
        store_generation.set_connected(True)

    def _on_disconnected(self) -> None:
        store_generation.set_connected(False)


def ensure_started(*, factory: Callable[[], SnapshotListener] | None = None) -> SnapshotListener | None:
    """The process's snapshot listener, built and started once; None if starting failed."""
    global _listener
    if _listener is not None:
        return _listener
    with _lock:
        if _listener is None:
            try:
                listener = (factory or SnapshotListener)()
                listener.start()
            except Exception as exc:
                swallowed(log, "ops.admin.snapshot_listener", exc)
                return None
            _listener = listener
        return _listener


def stop() -> None:
    """Stop and forget the singleton (tests, shutdown); the snapshot is bypassed after."""
    global _listener
    with _lock:
        listener, _listener = _listener, None
    if listener is not None:
        listener.stop()
    store_generation.set_connected(False)


def _start_on_first_request() -> None:
    if _listener is not None or current_app.testing:
        return
    if getattr(config, "ADMIN_STORE_SNAPSHOT", "on") == "off":
        return
    ensure_started()


def install(app: Flask) -> None:
    """Start the listener from ``app``'s first real request. Called once by app.py."""
    app.before_request(_start_on_first_request)
