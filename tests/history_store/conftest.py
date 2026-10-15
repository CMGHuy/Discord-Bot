"""tests/history_store/: the v162 Alpaca history store.

Puts scripts/data (the alpaca_history package and the data CLIs) and
scripts/ops (market_cache_repair) on sys.path -- appended, so nothing already
importable is shadowed -- and gives every test its own empty store root.
No test here reads the real data/market_data/ or touches the network."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT / "scripts" / "data", ROOT / "scripts" / "ops"):
    if str(_path) not in sys.path:
        sys.path.append(str(_path))


@pytest.fixture
def store_root(tmp_path, monkeypatch):
    """An empty history store under tmp_path, selected through HISTORY_STORE_DIR."""
    root = tmp_path / "market_data"
    root.mkdir()
    monkeypatch.setenv("HISTORY_STORE_DIR", str(root))
    return root
