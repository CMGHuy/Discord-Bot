"""Serve the built Angular SPA from `static/app/`.

Spec v13 Decision 6. Same-origin with the API, which is not a convenience:
it is what lets sub-project 1 keep cookie auth with no CORS, and what lets
`EventSource` -- which cannot send headers -- authenticate at all.

**The workspace routes are an allow-list, not a catch-all.** A catch-all
`<path:anything>` returning index.html is the usual SPA wiring and it is
wrong here, because both UIs are live until cutover: it would swallow every
Jinja URL, every typo, and every future route into a 200 that renders the
SPA's own "not found". A mistyped `/api/v1/tradez` would come back as HTML
with status 200, which is the single most confusing failure a JSON client
can be handed. Six prefixes are named, and everything else still 404s the
way it did before this file existed.

The SPA is absent in development (`static/app/` is gitignored and produced
by the Dockerfile's frontend stage), so every route here answers 404 when
it has not been built. That is deliberate: the alternative -- a friendly
placeholder page -- is indistinguishable from a broken deploy.
"""
from __future__ import annotations

import logging
import os

from flask import Blueprint, send_from_directory

log = logging.getLogger("swing-bot.admin.spa")

spa = Blueprint("spa", __name__)

#: Where the Dockerfile's frontend stage lands the bundle.
APP_DIR = os.path.join(os.path.dirname(__file__), "static", "app")

#: The six workspaces. Detail views live under their workspace's prefix, so
#: `/trades/abc` and `/watchlist/AAPL` are covered by `trades` and `watchlist`.
#:
#: `cockpit` and `universe` are the pre-SR4/SR5 names, kept as prefixes on
#: purpose. They serve the same index.html, and the SPA's router redirects
#: them client-side to `/dashboard` and `/watchlist`. Dropping them would make
#: a bookmark or an open tab 404 at the server before Angular ever loaded,
#: which a client-side redirect cannot rescue. They come out at NG57.
WORKSPACES = (
    "dashboard", "trades", "analytics", "watchlist", "risk", "system",
    "cockpit", "universe",
)

#: Hashed filenames (`main-FWP2ASZR.js`) are immutable by construction: a
#: changed file gets a different name, so it can never need revalidating.
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"

#: index.html is the one file whose name never changes, and the one that
#: names all the others. Caching it is how a browser ends up asking for a
#: bundle that no longer exists, on a deploy that otherwise went fine.
INDEX_CACHE = "no-cache, no-store, must-revalidate"


def is_built() -> bool:
    return os.path.isfile(os.path.join(APP_DIR, "index.html"))


def serves_root() -> bool:
    """Whether `/` should hand over to the SPA — the `ADMIN_UI` flag (NG53).

    The flag decides ONE thing: what `/` answers with. Every Jinja route
    stays mounted in both modes, and the dashboard keeps its own
    `/dashboard` URL, so flipping the value back is a restart and nothing
    more. That is the rollback the whole two-release cutover rests on.

    An unbuilt bundle falls back to Jinja rather than redirecting into a
    404. This is the one place that fallback is right -- elsewhere in this
    module an unbuilt SPA answers 404 precisely so it cannot be mistaken for
    a working deploy -- because here the alternative is a site whose front
    door is broken while a perfectly good UI sits behind it. It is logged at
    WARNING for the same reason: silently serving the old UI when the flag
    says otherwise is exactly the kind of thing nobody notices for a week.
    """
    from swingbot import config

    if getattr(config, "ADMIN_UI", "spa") != "spa":
        return False
    if not is_built():
        log.warning(
            "ADMIN_UI=spa but %s has no index.html -- serving the Jinja "
            "dashboard at / instead. Build the frontend, or set ADMIN_UI=jinja "
            "to make this deliberate.", APP_DIR,
        )
        return False
    return True


def _index():
    if not is_built():
        # 404 rather than a placeholder: an un-built SPA and a broken
        # deployment should not look the same from a browser.
        return ("Not Found", 404)
    response = send_from_directory(APP_DIR, "index.html")
    response.headers["Cache-Control"] = INDEX_CACHE
    return response


@spa.route("/app/<path:filename>")
def asset(filename: str):
    """The bundle's own files, long-cached by content hash.

    Served from `/app/...` rather than the SPA's own base href so this
    cannot collide with the Jinja UI's `/static/...`, which is still live.
    """
    if not is_built():
        return ("Not Found", 404)
    response = send_from_directory(APP_DIR, filename)
    # index.html can be requested through this route too (as /app/index.html)
    # and must not inherit the immutable header -- its name is not hashed.
    response.headers["Cache-Control"] = (
        INDEX_CACHE if filename == "index.html" else IMMUTABLE_CACHE
    )
    return response


def register(app) -> None:
    """Mount the SPA routes, skipping any URL the Jinja UI still owns.

    **Two of the six collide today**, which the plan did not anticipate and
    the first implementation found as two failing tests. Both UIs run side
    by side until Phase 5, so one URL cannot serve both, and the Jinja route
    wins in each case -- by two different mechanisms, which is worth knowing
    because only one of them is this function's doing:

    - `/risk` is an exact duplicate of a rule in `app.py`, so the check
      below skips it. Registering it anyway would leave Werkzeug to pick
      between two identical rules by sort order rather than by intent.
    - `/trades/<path:_rest>` is NOT a duplicate string -- `app.py` has
      `/trades/<trade_id>` -- so it registers, and then loses on every
      single-segment URL because Werkzeug ranks the narrower converter
      first. `/trades/PLAN-1` reaches Jinja; `/trades/a/b`, which Jinja has
      no rule for, reaches the SPA. Harmless, since the SPA has no
      two-segment trade route either.

    Skipping beats renaming or prefixing the SPA's routes because it
    self-heals: when NG57 deletes the Jinja routes, `/risk` stops being
    taken and `/trades/<trade_id>` stops out-ranking us, and both start
    serving the SPA with no change to this file. The skip is logged, so
    "why does /risk still render the old page" is answerable from the log
    rather than from memory.

    In the browser none of this is visible while navigating -- the SPA
    routes those paths client-side. It shows only on a hard reload of
    /risk or a trade detail, which lands on the Jinja page until cutover.
    """
    app.register_blueprint(spa)

    taken = {rule.rule for rule in app.url_map.iter_rules()}

    for workspace in WORKSPACES:
        # Two rules per workspace: the bare path, and everything under it --
        # the latter is what makes /trades/:id and /universe/:symbol survive
        # a refresh instead of 404ing.
        for rule, endpoint, view in (
            (f"/{workspace}", f"spa_{workspace}", _index),
            (f"/{workspace}/<path:_rest>", f"spa_{workspace}_sub",
             lambda _rest: _index()),
        ):
            if rule in taken:
                log.info("SPA route %s not registered: the Jinja UI owns it", rule)
                continue
            app.add_url_rule(rule, endpoint, view)
