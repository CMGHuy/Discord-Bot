"""v226 regression pin: the default v146 attribution report and the script's
printed summary stay byte-identical while the stop-width study is added to the
same module. The digests were recorded at the pre-change HEAD (main e0739414);
a change to them is a regression, never a re-record."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from swingbot.core.analytics import expectancy_attribution as ea
from swingbot.core.market.strategy_types import HORIZONS

HK = next(iter(HORIZONS))
REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "reports" / "expectancy_attribution.py"
GENERATED_AT = "2026-11-12T00:00:00+00:00"

DEFAULT_REPORT_SHA256 = "fcf56996cb2b053c50d0aa81f6a054be4f0fbd1b4c943d7b90a12170726dd9bb"
DEFAULT_SUMMARY_SHA256 = "647acb364f3ee70e5f1dc18bc360bf8bfe13b8707d0f2d0375666f33eb0960fa"


def _rows(slope: float, n: int, start: dt.date) -> list[dict]:
    """Deterministic attribution rows (ROW_KEYS), 30 entry weeks from ``start``."""
    out = []
    for i in range(n):
        r = slope * (i / (n - 1) - 0.5) + ((i * 37) % 11 - 5) / 10.0
        points = {"MACD momentum": 10 if i >= n // 2 else 0,
                  "ADX trend strength": 7 if i % 5 == 0 else (15 if i % 2 else 0)}
        if i % 3 == 0:
            points["Tight stop penalty"] = -5
        out.append({
            "r": r, "r_gross": r + 0.03,
            "week": (start + dt.timedelta(weeks=i % 30)).isoformat(),
            "confidence_score": i, "confidence_level": 3 + (3 * i) // n,
            "confidence_points": points,
            "confidence_unevaluated": ["ADX trend strength"] if i % 5 == 0 else [],
            "confluence_count": 2 + i % 3,
            "regime2_state": "bull_quiet" if i % 4 else "bear_volatile",
            "rs_pctile": float(i % 100),
            "direction": "bullish" if i % 3 else "bearish", "horizon": HK,
            "earnings_sessions": i % 40 if i % 7 else None,
            "earnings_status": "known" if i % 7 else "unknown",
            "risk_reward_ratio": 1.5 + (i % 4) / 4.0,
        })
    return out


@pytest.fixture(autouse=True)
def few_resamples(monkeypatch):
    monkeypatch.setattr(ea, "N_RESAMPLES", 200)


def _report() -> dict:
    live = _rows(0.0, 120, dt.date(2026, 3, 2))
    train = _rows(0.6, 240, dt.date(2021, 1, 4))
    return ea.build_report(live, train, seed=42, generated_at=GENERATED_AT)


def _script():
    spec = importlib.util.spec_from_file_location("v226_default_pin_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_the_default_report_is_byte_identical_to_the_pre_change_head():
    report = _report()
    assert report["verdict"] == "WEAK" and report["looks"] == 46     # sanity: the fixture is live
    assert _sha256(json.dumps(report, sort_keys=True, default=str)) == DEFAULT_REPORT_SHA256


def test_the_script_summary_is_byte_identical_to_the_pre_change_head():
    assert _sha256(_script().summary(_report())) == DEFAULT_SUMMARY_SHA256


def test_the_default_report_carries_no_stop_width_key():
    """The study writes its own report; the default one never grows a key."""
    report = _report()
    assert list(report) == ["generated_at", "verdict", "verdict_of_record", "looks",
                            "seed", "provenance", "populations"]
    assert "stop_atr" not in json.dumps(report)
