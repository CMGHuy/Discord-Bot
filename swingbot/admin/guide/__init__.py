"""v235: the Insights -> Guide content layer.

chapters.py loads docs/guide/NN-<slug>.md; placeholders.py resolves the fixed
{{name}} whitelist (live_risk.py, live_market.py). Nothing here writes, and
nothing here imports swingbot.admin.app: api_v1/guide.py is the only caller.
"""
