"""
Backward-compat shim.  Real code lives in swingbot.core.scanning.engine.

All of the following patterns still work unmodified:
    from swingbot.core import scan_engine          # module-level attribute access
    from swingbot.core.scan_engine import ScanItem # named import
    import swingbot.core.scan_engine as se         # aliased import
"""
from swingbot.core.scanning.engine import *   # noqa: F401,F403
