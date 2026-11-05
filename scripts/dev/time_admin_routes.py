"""v204 measure-first: test persisted FX alone on Analytics and Calendar.

The ledger keeps a route on the request path when five warm timings peak
at 0.5 s or less and five cold timings peak at 1.0 s or less. Run with
DATABASE_URL pointing to the local swing-db replica.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROUTES = {
    "analytics.performance": "/api/v1/analytics/performance",
    "analytics.equity_curve": "/api/v1/analytics/equity-curve",
    "calendar.pnl": "/api/v1/calendar/pnl",
}
RUNS = 5
WARM_MAX_S = 0.5
COLD_MAX_S = 1.0
ROOT = Path(__file__).resolve().parents[2]
NETWORK: tuple[tuple[str, str], ...] = (
    ("swingbot.core.marketdata.yf_safe", "download"),
    ("swingbot.core.marketdata.data", "get_quote_batch"),
    ("swingbot.core.marketdata.data", "get_current_price"),
    ("swingbot.core.marketdata.data", "get_current_price_batch"),
    ("swingbot.core.marketdata.data", "prefetch_prices"),
    ("swingbot.core.marketdata.data", "get_daily_data"),
    ("swingbot.core.marketdata.data", "get_daily_data_batch"),
    ("swingbot.core.marketdata.data", "_provider_currency_code"),
    ("swingbot.core.marketdata.data_refresh", "refresh_symbol"),
    ("swingbot.core.marketdata.fx", "_refreshed_frame"),
)


class NetworkDefect(RuntimeError):
    """A timed request tried a forbidden market-data operation."""


def verdict(warm: Sequence[float], cold: Sequence[float]) -> str:
    if warm and cold and max(warm) <= WARM_MAX_S and max(cold) <= COLD_MAX_S:
        return "request"
    return "snapshot"


def _poison(name: str, calls: list[str]):
    def forbidden(*args, **kwargs):
        calls.append(name)
        raise AssertionError(name)

    return forbidden


@contextmanager
def poisoned_network() -> Iterator[list[str]]:
    calls = []
    originals = []
    try:
        for module_name, attr in NETWORK:
            module = importlib.import_module(module_name)
            originals.append((module, attr, getattr(module, attr)))
            setattr(module, attr, _poison(f"{module_name}.{attr}", calls))
        yield calls
    finally:
        for module, attr, original in reversed(originals):
            setattr(module, attr, original)


def timed_get(client, path: str) -> float:
    start = time.perf_counter()
    response = client.get(path)
    seconds = time.perf_counter() - start
    if response.status_code != 200:
        raise RuntimeError(f"{path} -> {response.status_code}")
    return seconds


def measure_warm(client, path: str, runs: int = RUNS) -> list[float]:
    timed_get(client, path)
    return [timed_get(client, path) for _ in range(runs)]


def _login_failed() -> None:
    print("login failed", file=sys.stderr)
    raise SystemExit(3)


def measure_cold(route: str, runs: int = RUNS) -> list[float]:
    times = []
    for _ in range(runs):
        try:
            child = subprocess.run(
                [sys.executable, __file__, "--cold-one", route],
                capture_output=True, text=True, check=True,
            )
        except subprocess.CalledProcessError as exc:
            if exc.returncode == 3:
                _login_failed()
            raise
        result = json.loads(child.stdout.splitlines()[-1])
        if result["network"]:
            raise NetworkDefect(", ".join(result["network"]))
        if result["seconds"] is None:
            raise RuntimeError(f"{ROUTES[route]} -> cold request failed")
        times.append(result["seconds"])
    return times


def render(results: Mapping[str, Mapping[str, Sequence[float]]]) -> str:
    table = [
        "| route | warm runs (s) | warm max | cold runs (s) | cold max | verdict |",
        "| --- | --- | ---: | --- | ---: | --- |",
    ]
    verdicts = []
    for route in ROUTES:
        warm, cold = results[route]["warm"], results[route]["cold"]
        warm_max, cold_max = max(warm, default=0), max(cold, default=0)
        choice = verdict(warm, cold)
        warm_runs = ", ".join(f"{seconds:.3f}" for seconds in warm) or "—"
        cold_runs = ", ".join(f"{seconds:.3f}" for seconds in cold) or "—"
        table.append(
            f"| `{route}` | {warm_runs} | {warm_max:.3f} | "
            f"{cold_runs} | {cold_max:.3f} | {choice} |"
        )
        verdicts.append(
            f"- `{route}`: **{choice}** (warm max {warm_max:.3f} s, cold max {cold_max:.3f} s)"
        )
    return "\n".join([*table, "", *verdicts, ""])


def _replica_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    target = urlsplit(url)
    if (
        target.scheme != "postgresql+psycopg"
        or target.hostname not in {"localhost", "127.0.0.1"}
        or target.port != 56789
        or target.path != "/swingbot_prod_replica"
        or target.query
    ):
        raise SystemExit("DATABASE_URL must point to the local swing-db replica")
    return url


def _client():
    database_url = _replica_url()
    from swingbot import config

    # Config loads .env with override=True. Preserve the explicit replica
    # target for the app and for each cold subprocess it will spawn.
    os.environ["DATABASE_URL"] = config.DATABASE_URL = database_url
    config.ADMIN_REFRESHER = config.MARKETDATA_LAYER = "on"

    from swingbot.admin.app import app

    client = app.test_client()
    username, password = os.getenv("ADMIN_USERNAME"), os.getenv("ADMIN_PASSWORD")
    if not username or not password:
        _login_failed()
    response = client.post("/api/v1/session", json={"username": username, "password": password})
    if response.status_code != 200:
        _login_failed()
    return client


def _cold_one(route: str) -> int:
    client = _client()
    with poisoned_network() as calls:
        try:
            seconds = timed_get(client, ROUTES[route])
        except Exception:
            seconds = None
    print(json.dumps({"seconds": seconds, "network": calls}))
    return 0


def _warm_samples(client, path: str) -> list[float]:
    with poisoned_network() as calls:
        try:
            samples = measure_warm(client, path)
        finally:
            if calls:
                raise NetworkDefect(", ".join(calls)) from None
    return samples


def _write_results(out: Path, body: str) -> None:
    from sqlalchemy import text

    from swingbot.core.db.engine import get_engine

    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    with get_engine().connect() as conn:
        trades, closed = conn.execute(text(
            "SELECT count(*), count(*) FILTER (WHERE status != 'open') FROM trades"
        )).one()
        quote_currencies = conn.execute(text("SELECT count(*) FROM quote_currencies")).scalar_one()
        revision = ", ".join(conn.execute(text(
            "SELECT version_num FROM alembic_version ORDER BY version_num"
        )).scalars())
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out.write_text(
        "# v204 measure-first: Analytics and Calendar under persisted FX alone\n\n"
        "**Plan:** v204 task V204-2. **Rule:** `request` when warm max ≤ 0.5 s "
        "and cold max ≤ 1.0 s over 5 runs each; else `snapshot`.\n"
        f"**Run:** {stamp}, commit {commit}, replica restored [restore date], alembic "
        f"{revision}, `ADMIN_REFRESHER=on`, network poisoned (no call recorded).\n"
        f"**Book:** {trades} trades ({closed} closed), {quote_currencies} persisted quote currencies.\n\n"
        f"{body}",
        encoding="utf-8",
    )


def _measure_all(out: Path | None) -> int:
    client = _client()
    results = {}
    try:
        for route, path in ROUTES.items():
            print(f"Measuring {route}", file=sys.stderr, flush=True)
            warm = _warm_samples(client, path)
            results[route] = {"warm": warm, "cold": measure_cold(route)}
    except NetworkDefect as exc:
        print(exc, file=sys.stderr)
        return 2
    body = render(results)
    print(body, end="")
    if out is not None:
        _write_results(out, body)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--cold-one", choices=ROUTES)
    mode.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.cold_one:
        return _cold_one(args.cold_one)
    return _measure_all(args.out)


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
