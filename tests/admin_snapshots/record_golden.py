"""Record the six request-time payloads once from a seeded golden book."""
from __future__ import annotations

import json
from pathlib import Path

from tests.admin_snapshots.golden_book import GOLDEN_DIR, GOLDEN_MONTH, GOLDEN_NAMES, normalise

# Capture the analytics snapshot before the sparkline reads it.
CAPTURE_PATHS = {
    "risk": "/api/v1/risk",
    "performance_main": "/api/v1/analytics/performance?ledger=main",
    "equity_curve_main": "/api/v1/analytics/equity-curve?ledger=main",
    "calendar_pnl": f"/api/v1/calendar/pnl?month={GOLDEN_MONTH}",
    "analytics_snapshot": "/api/v1/analytics/snapshot?fresh=1",
}


def capture(client) -> dict[str, dict]:
    from swingbot.admin.api_v1 import dashboard

    payloads: dict[str, dict] = {}
    for name, path in CAPTURE_PATHS.items():
        response = client.get(path)
        assert response.status_code == 200, (name, response.get_data(as_text=True))
        body = response.get_json()
        assert body, f"{name} returned an empty payload"
        payloads[name] = body
    payloads["sparkline"] = dashboard._equity_30d()
    return payloads


def write(payloads: dict[str, dict], directory: Path = GOLDEN_DIR) -> list[Path]:
    directory.mkdir(exist_ok=True)
    paths = {name: directory / f"{name}.json" for name in GOLDEN_NAMES}
    for path in paths.values():
        if path.exists():
            raise FileExistsError(f"{path} is frozen (v204 V204-1). Fix the code.")
    for name, path in paths.items():
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(normalise(payloads[name]), indent=2, sort_keys=True) + "\n")
    return list(paths.values())
