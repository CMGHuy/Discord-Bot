"""fetch_json(): HTTP GET with a TTL disk cache under data/macro/cache/.

Degradation ladder (the contract every provider inherits):
  fresh cache            -> served, no network
  expired + fetch ok     -> refreshed
  expired + fetch FAIL   -> stale payload served, LAST_SERVED_STALE set
  no cache + fetch FAIL  -> None
Never raises toward a caller.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time

import requests

from swingbot import config
from swingbot.core.jsonio import atomic_write_json, read_json

log = logging.getLogger("swing-bot.macro.httpcache")

CACHE_DIR = os.path.join(config.DATA_DIR, "macro", "cache")

# Set whenever an expired-but-cached payload was served because the
# network failed; the snapshot builder (G38) reads and resets it.
LAST_SERVED_STALE = False


def _cache_key(url: str, params: dict | None) -> str:
    # sha1 of url+sorted params: api_key/token values never appear in
    # filenames in readable form (secrets contract).
    blob = url + "|" + json.dumps(sorted((params or {}).items()))
    return hashlib.sha1(blob.encode()).hexdigest()


def fetch_json(url, *, params=None, ttl_s=3600, timeout_s=5.0, cache_key=None):
    global LAST_SERVED_STALE
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = cache_key or _cache_key(url, params)
    path = os.path.join(CACHE_DIR, f"{key}.json")
    cached = read_json(path, default=None)
    now = time.time()
    if cached is not None and now - cached.get("fetched_at", 0) < ttl_s:
        return cached["payload"]
    try:
        resp = requests.get(url, params=params, timeout=timeout_s)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001 — every failure degrades, never raises
        # Log the exception TYPE and the bare path only — params (which
        # carry api keys) and query strings are never logged.
        log.warning("macro fetch failed (%s): %s", type(exc).__name__, url.split("?")[0])
        if cached is not None:
            LAST_SERVED_STALE = True
            return cached["payload"]
        return None
    atomic_write_json(path, {"fetched_at": now, "payload": payload})
    return payload


def purge_cache(max_age_days: int = 30) -> int:
    """Remove cache files older than max_age_days; returns count removed."""
    if not os.path.isdir(CACHE_DIR):
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for name in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, name)
        if os.path.getmtime(path) < cutoff:
            os.remove(path)
            removed += 1
    return removed
