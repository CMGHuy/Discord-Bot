"""
Backward-compat shim.  Real code lives in swingbot.core.scanning.embeds.
Existing imports like
    from swingbot.core.scan_embeds import build_embed, CONFIDENCE_COLORS
continue to work without modification.
"""
from swingbot.core.scanning.embeds import *   # noqa: F401,F403
