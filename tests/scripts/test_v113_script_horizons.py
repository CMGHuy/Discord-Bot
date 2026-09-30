"""v113: no script iterates HORIZONS -- closed measurements stay on the ten legacy horizons."""
from tests.horizon_iteration import ROOT, offenders


def test_no_script_iterates_horizons():
    assert offenders(sorted((ROOT / "scripts").rglob("*.py")), set()) == []
