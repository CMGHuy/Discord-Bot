"""
Backward-compat shim.  Real code lives in swingbot.core.scanning.confidence.
This file exists so existing imports like
    from swingbot.core.confidence import ConfidenceResult, score_confidence
continue to work without modification.
"""
from swingbot.core.scanning.confidence import *   # noqa: F401,F403
