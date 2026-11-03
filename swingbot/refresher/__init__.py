"""v201: the admin market refresher process.

Run as ``python -m swingbot.refresher`` (its own compose service). It keeps the
admin pages' quotes warm so a page load never fetches. Never imported by the
bot or the admin app.
"""
