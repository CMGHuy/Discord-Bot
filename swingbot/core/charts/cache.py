# swingbot/core/charts/cache.py
"""
Content-hash PNG cache for expensive chart renders. A closed trade's
chart never changes once the trade is closed (same OHLCV window, same
levels), so re-rendering it every time !trade/tradecharts/a Discord
button asks for it is pure waste -- this caches by a hash of whatever
"identity" fields the caller considers immutable (trade_id + closed_at
+ a schema version number, so a future chart-format change still
busts every old cache entry automatically), not by a TTL.
"""
import hashlib
import json
import os
import time
from typing import Callable

from swingbot import config

DEFAULT_CACHE_DIR = os.path.join(config.EXPORT_DIR, "chart_cache")


def _key_hash(key_parts: dict) -> str:
    canonical = json.dumps(key_parts, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def cached_chart(key_parts: dict, render_fn: Callable[[str], str], cache_dir: str = None) -> str:
    """Returns the cached PNG path for `key_parts` if it already exists;
    otherwise calls `render_fn(target_path)` (which must write to
    `target_path` and return it, matching every existing chart-render
    function's own `(..., out_dir, filename) -> path` shape when given
    that this function IS effectively picking out_dir/filename for it)
    and returns the freshly rendered path."""
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)
    key = _key_hash(key_parts)
    target_path = os.path.join(cache_dir, f"{key}.png")
    if os.path.exists(target_path):
        return target_path
    return render_fn(target_path)


def purge(max_age_days: int = 7, cache_dir: str = None) -> int:
    """Deletes every cached PNG whose mtime is older than max_age_days.
    Returns the count removed. Safe to call every scan cycle -- a
    directory listing + stat per file is negligible next to a single
    chart render."""
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    if not os.path.isdir(cache_dir):
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for name in os.listdir(cache_dir):
        path = os.path.join(cache_dir, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
                removed += 1
        except OSError:
            continue
    return removed
