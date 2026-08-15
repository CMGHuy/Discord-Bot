"""
swingbot.core.scanning — the full scan pipeline.

Sub-modules
-----------
confidence  Confidence scoring (ConfidenceResult, score_confidence)
regime      Market-regime + HTF-EMA bias filter
embeds      Discord embed builders (was scan_embeds.py)
engine      Scan loop, ScanItem, all public scanning entry-points
            (was scan_engine.py)

No backward-compat shims remain at swingbot/core/{confidence,regime,
scan_embeds,scan_engine}.py — the last of them, scan_engine.py, was
deleted in the v27 repo restructure (plan Task 14). Every call site now
imports the submodule directly.

This __init__ is intentionally empty of imports: sub-modules import
discord and other heavy deps at module level, so importing all of them
eagerly here (even transitively via a shim) would break any lightweight
utility that only needs, say, ConfidenceResult, and would also cause
circular-import issues during startup.  Import the submodule you need
directly:
    from swingbot.core.scanning.confidence import ConfidenceResult
    from swingbot.core.scanning import engine
"""
