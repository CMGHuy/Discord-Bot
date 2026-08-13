"""Dump the REAL /api/v1/market/chart payload for each SR32 chart fixture.

SR40 step 4 needs the browser and the PNG drawing the same trade. The PNG
side is `scripts/render_chart_fixtures.py`; this is the other side, and it
goes through the actual Flask route rather than reassembling the payload,
so what the harness draws is what the endpoint would serve.

The route's only two seams are `_ohlcv_frame` and `_trade_for_levels` -- the
same two `tests/admin/test_api_v1_market.py` patches. The fixture's horizon
dict is injected into HORIZONS under a private key, because the endpoint
reads horizons by key while the fixtures pass them literally.

The browser half is `frontend/chart-harness/` — see its README for the full
four-command loop.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(tempfile.gettempdir(), "chart-payloads")

sys.path.insert(0, ROOT)
os.chdir(ROOT)

# Point every data-dir-derived path at a scratch directory BEFORE any admin
# module is imported -- they bake it in at import time (see tests/admin/conftest).
from swingbot import config  # noqa: E402

config.DATA_DIR = tempfile.mkdtemp(prefix="chart-harness-")

from swingbot.admin import app as admin_app  # noqa: E402
from swingbot.core.strategy_types import HORIZONS  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "scripts"))
from render_chart_fixtures import FIXTURES  # noqa: E402

os.makedirs(OUT, exist_ok=True)
client = admin_app.app.test_client()
client.post("/api/v1/session", json={"username": "admin", "password": "admin"})

written = []
for name in sorted(FIXTURES):
    df, kwargs = FIXTURES[name]
    last = float(df["Close"].iloc[-1])
    key = f"_fixture_{name}"
    HORIZONS[key] = dict(kwargs.get("horizon") or {})

    trade = {
        "id": name,
        "ticker": "FIXT",
        # The same levels render_chart_fixtures.py hands generate_trade_chart.
        "entry": last,
        "stop_loss": last * 0.94,
        "take_profit": last * 1.08,
        "target2_price": last * 1.14,
        "working_stop": None,
        "direction": "bullish",
        "horizon_key": key,
        "target_sources": kwargs.get("target_sources") or [],
        "stop_sources": kwargs.get("stop_sources") or [],
    }

    admin_app._ohlcv_frame = lambda ticker, _df=df: _df
    admin_app._trade_for_levels = lambda tid, _t=trade: _t

    response = client.get(f"/api/v1/market/chart/{name}?window={len(df)}")
    if response.status_code != 200:
        print(f"  {name}: HTTP {response.status_code} {response.get_data(as_text=True)[:120]}")
        continue

    payload = response.get_json()
    path = os.path.join(OUT, f"{name}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    overlay = payload.get("overlay")
    print(f"  {name}: {len(payload['ohlcv'])} bars, "
          f"overlay={overlay['shape']['kind'] if overlay else None}, "
          f"indicators={sorted(payload['indicators'])}, "
          f"profile={len(payload['volume_profile'])}")
    written.append(name)

print(f"wrote {len(written)} payloads to {OUT}")
