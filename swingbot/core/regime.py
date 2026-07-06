"""
Backward-compat shim.  Real code lives in swingbot.core.scanning.regime.
Existing imports like
    from swingbot.core.regime import get_market_regime, get_htf_bias
continue to work without modification.
"""
from swingbot.core.scanning.regime import *   # noqa: F401,F403
