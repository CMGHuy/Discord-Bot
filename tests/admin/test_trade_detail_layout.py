"""NG19 TRIAGE — **HTML-structure · DELETE at cutover.**

The single assertion here is about source ORDER within the rendered trade
detail page: the static PNG appears before the interactive chart, so the page
shows something while lightweight-charts boots. In the SPA that ordering is a
component-template concern owned by sub-project 4, and the PNG route it
depends on is itself a pending drop (spec v11). Nothing about the domain is
asserted, so there is nothing to migrate.
"""


