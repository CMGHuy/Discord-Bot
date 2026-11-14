"""v218 P3-c: the build a response came from -- the first input of every ETag.

``build_version()`` is the SHA-256 of ``VERSION.json``'s bytes (16 hex chars)
plus the image tag ``SWING_BOT_IMAGE`` when the environment carries it. On
the VM the admin container does NOT carry it: ``deploy/deploy.sh`` only
exports it to the shell running compose and ``docker-compose.yml`` does not
forward it to the admin service (v206 spec, Plan 3 build tag on the VM). So
today the build input is the ``VERSION.json`` hash alone, and two images with
the same ``VERSION.json`` share tags. It is read from ``os.environ`` because
it is not a ``config.FIELDS`` entry.

Cached per process: the image cannot change under a running worker. A
missing ``VERSION.json`` raises and caches nothing -- the ETag code swallows
that and sends no tag, never a tag that cannot tell two builds apart.
Imports nothing from ``swingbot.admin``, so ``api_v1`` modules may import it.
"""
from __future__ import annotations

import hashlib
import os
import threading

from swingbot import config

VERSION_PATH = os.path.join(config._PROJECT_ROOT, "VERSION.json")
IMAGE_ENV = "SWING_BOT_IMAGE"

_LOCK = threading.Lock()
_CACHE: str | None = None


def build_version() -> str:
    """``"<sha256(VERSION.json)[:16]>|<image tag or ''>"``; raises OSError without the file."""
    global _CACHE
    cached = _CACHE
    if cached is not None:
        return cached
    with _LOCK:
        if _CACHE is None:
            _CACHE = _compute()
        return _CACHE


def _compute() -> str:
    with open(VERSION_PATH, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()[:16]
    return f"{digest}|{os.environ.get(IMAGE_ENV, '')}"


def reset_cache() -> None:
    """Forget the cached value (tests; never needed in a running worker)."""
    global _CACHE
    with _LOCK:
        _CACHE = None
