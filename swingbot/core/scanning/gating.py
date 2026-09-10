"""Shared confluence gate arithmetic for live scans and historical replay."""
from swingbot.scan_params import ScanParams


def scenario_gate_inputs(params: ScanParams, horizon: dict) -> dict:
    return {
        "min_reward_pct": max(params.min_reward_pct, horizon.get("sr_target_min_pct", 0) * 0.15),
        "min_stop_distance_pct": params.min_stop_distance_pct,
        "max_stop_distance_pct": max(params.max_stop_loss_pct, horizon.get("max_risk_pct", 0)),
        "min_risk_reward": params.min_risk_reward_ratio,
    }


def passes_confluence(n_confluent: int, params: ScanParams) -> bool:
    return n_confluent >= params.min_target_confluence_count
