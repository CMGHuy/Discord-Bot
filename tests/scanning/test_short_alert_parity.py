"""V118-6: a new-lane SHORT alert carries the same borrow-check text, decision
date and plan numbers in the full Discord embed, the simple mirror (ticket and
legacy form) and the email/push body -- and a base alert carries none of it."""
import dataclasses

import pytest

from swingbot import config
from swingbot.core.infra import notifier
from swingbot.core.presentation import short_notice
from swingbot.core.scanning import execution_embeds
from swingbot.core.scanning.alert_embeds import build_embed, build_simple_alert
from tests.scanning.test_embeds_v3 import (PERF_STATS_EMPTY, make_item, make_plan_v2,
                                           _isolated_scan_snapshots)  # noqa: F401

CONTEXT = {"source": "short_universe", "mode": "isolated",
           "reference_id": "ref-1", "decision_bar_date": "2026-10-01"}


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(execution_embeds, "_sizing_snapshot", lambda entry, plan: None)
    monkeypatch.setattr(short_notice, "completed_session_date", lambda: "2026-10-01")


def _short_item(context=CONTEXT):
    plan_v2 = dataclasses.replace(make_plan_v2(direction="bearish"), stop_loss=98.25)
    item = make_item(plan_v2=plan_v2)
    item.plan.stop_loss = 96.0       # scenario stop; the clamped 98.25 is the source of truth
    item.candidate_context = context
    return item


def _embed_text(embed):
    return "\n".join([embed.description or "", *(f.name + "\n" + f.value for f in embed.fields)])


def _full(item):
    return _embed_text(build_embed(item, "x", PERF_STATS_EMPTY, None, None))


def _renderings(item):
    body = notifier._build_alert_texts(item, item.plan, item.conf)[1]
    return {"discord": _full(item), "simple": _embed_text(build_simple_alert(item)),
            "email/push": body}


def test_every_surface_carries_borrow_mode_date_and_the_clamped_numbers():
    for name, text in _renderings(_short_item()).items():
        assert "CHECK BORROW AVAILABILITY" in text, name
        assert "2026-10-01" in text and "isolated" in text.lower(), name
        assert "98.25" in text and "110.00" in text, name
        assert "expires" in text.lower() and "5 bars" in text, name
        assert "STALE" not in text, name


def test_the_legacy_simple_form_carries_it_too(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "off")
    item = _short_item()
    text = _embed_text(build_simple_alert(item))
    assert "CHECK BORROW AVAILABILITY" in text and "isolated" in text.lower()


def test_a_stale_decision_bar_is_labelled_on_every_surface(monkeypatch):
    monkeypatch.setattr(short_notice, "completed_session_date", lambda: "2026-10-02")
    for name, text in _renderings(_short_item()).items():
        assert "STALE" in text and "2026-10-01" in text, name


def test_a_base_alert_carries_no_borrowed_metadata():
    for name, text in _renderings(_short_item(context=None)).items():
        assert "BORROW" not in text and "SHORT execution check" not in text, name


def test_email_and_push_receive_the_same_notice(monkeypatch):
    sent = {}
    monkeypatch.setattr(config, "ALERT_EMAIL_ENABLED", True)
    monkeypatch.setattr(config, "ALERT_PUSH_ENABLED", True)
    monkeypatch.setattr(config, "ALERT_EMAIL_TO", "a@b.c")
    monkeypatch.setattr(config, "SMTP_USER", "u")
    monkeypatch.setattr(config, "SMTP_PASSWORD", "p")
    monkeypatch.setattr(config, "NTFY_TOPIC", "t")
    monkeypatch.setattr(config, "SECONDARY_ALERT_MIN_CONFIDENCE", 1)
    monkeypatch.setattr(notifier, "_send_email", lambda s, b: sent.setdefault("email", b))
    monkeypatch.setattr(notifier, "_send_push", lambda title, message, **kw: sent.setdefault("push", message))
    item = _short_item()
    notifier.notify_secondary(item, item.plan, item.conf)
    assert set(sent) == {"email", "push"}
    assert all("CHECK BORROW AVAILABILITY" in body for body in sent.values())


def test_the_notice_never_claims_a_verified_locate():
    text = short_notice.short_lane_notice(
        CONTEXT, {"entry": 100.0, "stop_loss": 98.25, "take_profit": 90.0}, 5)
    assert "not a verified locate" in text.lower()
