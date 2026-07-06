"""
swingbot.core.scanning — the full scan pipeline.

Sub-modules
-----------
confidence  Confidence scoring (ConfidenceResult, score_confidence)
regime      Market-regime + HTF-EMA bias filter
embeds      Discord embed builders (was scan_embeds.py)
engine      Scan loop, ScanItem, all public scanning entry-points
            (was scan_engine.py)

Backward-compat shims at swingbot/core/{confidence,regime,scan_embeds,
scan_engine}.py re-export everything from here so existing code that
does `from swingbot.core.scan_engine import …` or
`from swingbot.core import scan_engine` keeps working unmodified.

This __init__ is intentionally empty of imports: sub-modules import
discord and other heavy deps at module level, so importing all of them
eagerly here (even transitively via a shim) would break any lightweight
utility that only needs, say, ConfidenceResult, and would also cause
circular-import issues during startup.  Import the submodule you need
directly:
    from swingbot.core.scanning.confidence import ConfidenceResult
    from swingbot.core.scanning import engine
"""
