"""GET /api/v1/reports/* — the v146 and v147 results behind the Reports page.

Display only. Neither endpoint computes a figure, applies a floor or reshapes
a field: each calls one loader and wraps its return value.

    { "status": "ok" | "not_run", "generated_at": str | null, "result": {...} | null }

`not_run` is a 200, not a 404: the endpoint is answering truthfully that
nothing has been produced yet, and the page renders that as a state. A loader
that raises is different. The report writers replace their file atomically
(temp file + `os.replace`), so a file that is present but unreadable is never
a half-written one; it is a real fault and surfaces as a 500 rather than
hiding behind `not_run`.

No request runs a backtest or builds a report. The results are produced by
scripts run on the VM (`docs/deploy/DEPLOY_HETZNER.md`); `data/` is mounted
into both containers, so a new run is visible here without a restart.
"""
from __future__ import annotations

from typing import Callable

from flask import jsonify

from . import ApiError, api_v1
from .auth import require_auth


def _load_attribution() -> dict | None:
    # Imported on call, and from the light infra stores (v146/v147), never from
    # swingbot.core.analytics, whose package __init__ pulls pandas/numpy.
    from swingbot.core.infra import expectancy_attribution_store

    return expectancy_attribution_store.load_latest()


def _load_gates() -> dict | None:
    from swingbot.core.infra import gate_counterfactual_store

    return gate_counterfactual_store.load_report()


def _envelope(load: Callable[[], dict | None]):
    try:
        result = load()
    except Exception as exc:  # noqa: BLE001 - any loader failure is the same 500
        raise ApiError("report_unreadable", f"{type(exc).__name__}: {exc}", 500) from exc
    if result is None:
        return jsonify({"status": "not_run", "generated_at": None, "result": None})
    return jsonify({"status": "ok", "generated_at": result.get("generated_at"),
                    "result": result})


@api_v1.route("/reports/expectancy-attribution", methods=["GET"])
@require_auth
def report_expectancy_attribution():
    return _envelope(lambda: _load_attribution())


@api_v1.route("/reports/gate-counterfactual", methods=["GET"])
@require_auth
def report_gate_counterfactual():
    return _envelope(lambda: _load_gates())
