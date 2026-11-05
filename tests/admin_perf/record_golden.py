"""Record the v205 admin goldens ONCE, from today's code:

    python -m tests.admin_perf.record_golden

Writes golden/<name>.json only where it is missing; an existing golden is frozen
and never rewritten. A failing golden means the code is fixed, never the golden."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.admin_perf import golden_book as gb


def write_golden(name: str, payload) -> bool:
    path = gb.golden_path(name)
    if path.exists():
        return False
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    return True


def main() -> int:
    if all(gb.golden_path(name).exists() for name in gb.ENDPOINTS):
        print("every golden exists; nothing recorded (they are frozen)")
        return 0
    os.environ["ADMIN_PERF_RECORD"] = "1"
    test = Path(__file__).with_name("test_golden_endpoints.py")
    return int(pytest.main(["-q", "-n", "0", f"{test}::test_endpoint_matches_its_frozen_golden"]))


if __name__ == "__main__":
    raise SystemExit(main())
