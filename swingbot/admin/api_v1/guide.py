"""GET /api/v1/guide and /api/v1/guide/<slug> -- the Insights -> Guide chapters (v235).

Chapters are Markdown files in docs/guide/ that ship in the image (`COPY . .`),
so what this serves is the guide as of the deployed build. The files are read
once per process (`_chapters`, lru_cache); `{{name}}` placeholders resolve on
every request, so live values (a hot-reloaded cap, alerts per week) are current.

Failure is loud and never leaks raw text: a malformed chapter is 500
`guide_invalid`; a placeholder outside the whitelist is 500 `guide_placeholder`
with the name logged here, never echoed. Viewer-readable (not in
access.ADMIN_ONLY_PREFIXES): the guide explains the bot, it changes nothing.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from flask import jsonify

from swingbot.admin.guide import chapters as _chapters_mod
from swingbot.admin.guide import placeholders as _placeholders
from swingbot.admin.guide.chapters import Chapter

from . import ApiError, api_v1
from .auth import require_auth

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _chapters() -> tuple[Chapter, ...]:
    return tuple(_chapters_mod.load_chapters())


def clear_cache() -> None:
    """Forget the cached chapter files (tests; a deploy restarts the process)."""
    _chapters.cache_clear()


def _loaded() -> tuple[Chapter, ...]:
    try:
        return _chapters()
    except _chapters_mod.GuideFormatError as exc:
        log.error("guide chapter invalid: %s", exc)
        raise ApiError("guide_invalid", "A guide chapter could not be read.", 500) from exc


def _resolved(chapter: Chapter) -> str:
    try:
        return _placeholders.resolve(chapter.body)
    except _placeholders.UnknownPlaceholder as exc:
        log.error("guide placeholder %r unknown in chapter %s", exc.name, chapter.slug)
        raise ApiError("guide_placeholder",
                       f"Guide chapter {chapter.slug} could not be rendered.", 500) from exc


def _summary(chapter: Chapter) -> dict[str, Any]:
    headings = _chapters_mod.extract_headings(_resolved(chapter))
    return {
        "slug": chapter.slug,
        "title": chapter.title,
        "order": chapter.order,
        "reviewed_for": chapter.reviewed_for,
        "headings": [{"level": h.level, "text": h.text, "anchor": h.anchor} for h in headings],
    }


@api_v1.route("/guide", methods=["GET"])
@require_auth
def guide_index():
    return jsonify({"chapters": [_summary(chapter) for chapter in _loaded()]})


@api_v1.route("/guide/<slug>", methods=["GET"])
@require_auth
def guide_chapter(slug: str):
    chapter = next((c for c in _loaded() if c.slug == slug), None)
    if chapter is None:
        raise ApiError("not_found", "No guide chapter has that name.", 404)
    return jsonify({
        "slug": chapter.slug,
        "title": chapter.title,
        "reviewed_for": chapter.reviewed_for,
        "markdown": _resolved(chapter),
    })
