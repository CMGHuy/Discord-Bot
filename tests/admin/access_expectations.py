"""v207: every Flask rule x method, classified for the viewer role.

The source of truth for who may call what (spec § Access check):
  "public" -- the role check does not apply: the /api/v1/session door and
              every non-v1 rule (SPA shell, assets).
  "viewer" -- a viewer may call it.
  "admin"  -- a viewer gets 403 forbidden.
test_access_contract.py fails when a served rule is missing here, when a row
names a rule that is gone, and when swingbot.admin.access disagrees with a
row. Adding a route means adding its row here: decide, don't default.
"""
V1 = "/api/v1"

#: The SPA shell serves /<workspace> and /<workspace>/<path:_rest> (spa.py).
SPA_WORKSPACES = ("analytics", "calendar", "cancels", "cockpit", "dashboard", "insights",
                  "plans", "reports", "research", "risk", "system", "trades", "ui",
                  "universe", "versions", "watchlist")

_PUBLIC = [
    ("/", "GET"), ("/<any('ngsw-worker.js', 'ngsw.json'):filename>", "GET"),
    ("/app/<path:filename>", "GET"), ("/static/<path:filename>", "GET"),
    (f"{V1}/session", "GET"), (f"{V1}/session", "POST"), (f"{V1}/session", "DELETE"),
    *[(f"/{w}", "GET") for w in SPA_WORKSPACES],
    *[(f"/{w}/<path:_rest>", "GET") for w in SPA_WORKSPACES],
]

#: Viewer-readable GETs. /market/chart backfills a trendline fit and
#: /market/tape records demand and refreshes stale quotes: idempotent cache
#: fills any reader triggers, never a change to the book (V207-7 audit).
_VIEWER_GET = [
    "/analytics/by-dimension", "/analytics/calibration", "/analytics/cohort",
    "/analytics/equity-curve", "/analytics/exit-quality", "/analytics/heat-grid",
    "/analytics/journal", "/analytics/override-fidelity", "/analytics/partials",
    "/analytics/performance", "/analytics/plans", "/analytics/registry",
    "/analytics/snapshot", "/analytics/soak", "/analytics/strategies",
    "/analytics/variance-band",
    "/calendar/pnl", "/calendar/pnl/day", "/calendar/pnl/day/sparklines",
    "/cancel-precision", "/dashboard", "/equity/candles", "/events", "/feed-posts",
    "/feed-posts/kinds", "/health", "/live",
    "/market/chart/<ticker>", "/market/tape", "/market/updates",
    "/reports/expectancy-attribution", "/reports/gate-counterfactual", "/research/ledger",
    "/risk", "/risk/killswitch", "/system/preferences", "/system/scan",
    "/trades", "/trades/<trade_id>", "/trades/<trade_id>/journal", "/trades/export.csv",
    "/watchlist/suggest", "/watchlist/tickers",
]

_ADMIN_GET = [
    "/analytics/tuning/proposals", "/jobs", "/jobs/<job_id>", "/jobs/<job_id>/result",
    "/jobs/tune/defaults", "/system/health", "/system/logs", "/system/logs/raw",
    "/system/settings", "/system/settings/export", "/versions",
]

#: Every v1 write except the session door.
_ADMIN_WRITES = [
    ("/analytics/tuning/proposals", "POST"), ("/analytics/tuning/proposals/<filename>", "DELETE"),
    ("/jobs/tune", "POST"), ("/market/refresh", "POST"), ("/risk/killswitch", "POST"),
    ("/system/bot/restart", "POST"), ("/system/logs", "DELETE"),
    ("/system/preferences", "PUT"), ("/system/scan/pause", "POST"),
    ("/system/scan/resume", "POST"), ("/system/scan/stop", "POST"),
    ("/system/scan/trigger", "POST"), ("/system/settings", "PUT"),
    ("/system/settings/import", "POST"), ("/system/settings/preview", "POST"),
    ("/trades/<trade_id>", "DELETE"), ("/trades/<trade_id>/cancel", "POST"),
    ("/trades/<trade_id>/close", "POST"), ("/trades/<trade_id>/note", "PUT"),
    ("/trades/clear-history", "POST"), ("/trades/clear-open", "POST"),
    ("/trades/close-open", "POST"), ("/watchlist/tickers", "POST"),
    ("/watchlist/tickers/<symbol>", "DELETE"),
]

#: v207 Users API (V207-6): admin-only by prefix, reads and writes alike.
_USERS = [
    ("/users", "GET"), ("/users", "POST"), ("/users/<int:user_id>", "PATCH"),
    ("/users/<int:user_id>", "DELETE"), ("/users/<int:user_id>/password", "POST"),
]

EXPECTATIONS: dict[tuple[str, str], str] = {
    **{key: "public" for key in _PUBLIC},
    **{(V1 + rule, "GET"): "viewer" for rule in _VIEWER_GET},
    **{(V1 + rule, "GET"): "admin" for rule in _ADMIN_GET},
    **{(V1 + rule, method): "admin" for rule, method in _ADMIN_WRITES},
    **{(V1 + rule, method): "admin" for rule, method in _USERS},
}

#: Rule with converters -> a concrete path that routes to it. "t1" and "AAPL"
#: are the ids V207-7's matrix seeds.
SAMPLE_PATHS: dict[str, str] = {
    "/<any('ngsw-worker.js', 'ngsw.json'):filename>": "/ngsw.json",
    "/app/<path:filename>": "/app/main.js",
    "/static/<path:filename>": "/static/app.css",
    **{f"/{w}/<path:_rest>": f"/{w}/x" for w in SPA_WORKSPACES},
    f"{V1}/analytics/tuning/proposals/<filename>": f"{V1}/analytics/tuning/proposals/p.json",
    f"{V1}/jobs/<job_id>": f"{V1}/jobs/j1",
    f"{V1}/jobs/<job_id>/result": f"{V1}/jobs/j1/result",
    f"{V1}/market/chart/<ticker>": f"{V1}/market/chart/AAPL",
    f"{V1}/trades/<trade_id>": f"{V1}/trades/t1",
    f"{V1}/trades/<trade_id>/cancel": f"{V1}/trades/t1/cancel",
    f"{V1}/trades/<trade_id>/close": f"{V1}/trades/t1/close",
    f"{V1}/trades/<trade_id>/journal": f"{V1}/trades/t1/journal",
    f"{V1}/trades/<trade_id>/note": f"{V1}/trades/t1/note",
    f"{V1}/watchlist/tickers/<symbol>": f"{V1}/watchlist/tickers/AAPL",
    f"{V1}/users/<int:user_id>": f"{V1}/users/1",
    f"{V1}/users/<int:user_id>/password": f"{V1}/users/1/password",
}
